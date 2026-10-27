// NOX V16 P02 candidate — one SQLite database for chat history and attachments.
// Requires Microsoft.Data.Sqlite (package/version must be pinned by Integrator #6).
// Trusted native host must supply tenant/principal; never trust WebView/website assertions.
using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Data.Sqlite;

namespace NoxHelion.P02;

public sealed record ChatMessage(string Id, string Role, string Content, string CreatedUtc);
public sealed record StoredAttachment(string Id, string StorageId, string Sha256, string Mime, long Bytes);
public sealed record ChatDeleteReceipt(string ChatId, IReadOnlyList<string> StorageIds);

public sealed class ChatSqliteStore
{
    private readonly string _connectionString;
    public const long MaxChatBytes = 100L * 1024 * 1024;
    public const long MaxFileBytes = 25L * 1024 * 1024;

    public ChatSqliteStore(string databasePath)
    {
        if (string.IsNullOrWhiteSpace(databasePath)) throw new ArgumentException("Database path is required.");
        var fullPath = Path.GetFullPath(databasePath);
        Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
        var builder = new SqliteConnectionStringBuilder
        {
            DataSource = fullPath, Mode = SqliteOpenMode.ReadWriteCreate,
            Cache = SqliteCacheMode.Shared, Pooling = true, ForeignKeys = true
        };
        _connectionString = builder.ToString();
    }

    private async Task<SqliteConnection> OpenAsync(CancellationToken ct)
    {
        var db = new SqliteConnection(_connectionString);
        try
        {
            await db.OpenAsync(ct).ConfigureAwait(false);
            db.DefaultTimeout = 10;
            return db;
        }
        catch { await db.DisposeAsync().ConfigureAwait(false); throw; }
    }

    public async Task InitializeAsync(CancellationToken ct = default)
    {
        await using var db = await OpenAsync(ct).ConfigureAwait(false);
        using (var version = db.CreateCommand())
        {
            version.CommandText = "PRAGMA user_version;";
            var v = Convert.ToInt32(await version.ExecuteScalarAsync(ct).ConfigureAwait(false));
            if (v > 1) throw new NotSupportedException("Newer chat database; refusing downgrade.");
            if (v == 1) return;
        }
        await using var tx = await db.BeginTransactionAsync(ct).ConfigureAwait(false);
        await using (var setup = db.CreateCommand())
        {
            setup.Transaction = (SqliteTransaction)tx;
            setup.CommandText = @"
CREATE TABLE IF NOT EXISTS chats (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, owner TEXT NOT NULL,
 created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
 content TEXT NOT NULL, created_utc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_messages_chat_created ON messages(chat_id,created_utc,id);
CREATE TABLE IF NOT EXISTS attachments (
 id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
 storage_id TEXT UNIQUE NOT NULL, sha256 TEXT NOT NULL,
 mime TEXT NOT NULL, size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
 created_utc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_attachments_chat ON attachments(chat_id);
PRAGMA user_version=1;";
            await setup.ExecuteNonQueryAsync(ct).ConfigureAwait(false);
        }
        await tx.CommitAsync(ct).ConfigureAwait(false);
    }

    private static string Required(string input, string name)
    {
        if (string.IsNullOrWhiteSpace(input) || input.Length > 256 ||
            input != input.Trim())
            throw new ArgumentException("Missing or invalid scope: " + name, name);
        return input;
    }

    private static SqliteParameter P(string key, object value) => new(key, value);

    private static void Scope(SqliteCommand c, string tenant, string principal, string chatId)
    {
        c.Parameters.AddRange(new[] { P("$tenant", Required(tenant,nameof(tenant))),
            P("$owner",Required(principal,nameof(principal))),
            P("$chat",Required(chatId,nameof(chatId))) });
    }

    public async Task CreateChatAsync(string tenant, string principal, string chatId, CancellationToken ct = default)
    {
        await using var db = await OpenAsync(ct).ConfigureAwait(false);
        await using var cmd = db.CreateCommand();
        cmd.CommandText = "INSERT INTO chats(id,tenant,owner,created_utc) VALUES($chat,$tenant,$owner,$at);";
        Scope(cmd,tenant,principal,chatId);
        cmd.Parameters.AddWithValue("$at",DateTimeOffset.UtcNow.ToString("O"));
        await cmd.ExecuteNonQueryAsync(ct).ConfigureAwait(false);
    }

    private static async Task EnsureOwnedAsync(SqliteConnection db, SqliteTransaction? tx,
        string tenant, string principal, string chatId, CancellationToken ct)
    {
        await using var cmd = db.CreateCommand();
        cmd.Transaction=tx;
        cmd.CommandText = "SELECT 1 FROM chats WHERE id=$chat AND tenant=$tenant AND owner=$owner;";
        Scope(cmd,tenant,principal,chatId);
        if (await cmd.ExecuteScalarAsync(ct).ConfigureAwait(false) is null)
            throw new UnauthorizedAccessException("Chat not available for current principal.");
    }

    public async Task<string> AddMessageAsync(string tenant, string principal, string chatId,
        string role, string content, CancellationToken ct = default)
    {
        if (role is not ("user" or "assistant" or "tool"))
            throw new ArgumentException("Invalid persisted role.",nameof(role));
        if (content is null || content.Length > 2_000_000)
            throw new ArgumentException("Message content outside quota.",nameof(content));
        await using var db=await OpenAsync(ct).ConfigureAwait(false);
        await using var tx=(SqliteTransaction)await db.BeginTransactionAsync(ct).ConfigureAwait(false);
        await EnsureOwnedAsync(db,tx,tenant,principal,chatId,ct).ConfigureAwait(false);
        var id=Guid.NewGuid().ToString("N");
        await using var cmd=db.CreateCommand();
        cmd.Transaction=tx;
        cmd.CommandText="INSERT INTO messages(id,chat_id,role,content,created_utc) VALUES($id,$chat,$role,$content,$at);";
        cmd.Parameters.AddRange(new[]{P("$id",id),P("$chat",chatId),P("$role",role),
            P("$content",content),P("$at",DateTimeOffset.UtcNow.ToString("O"))});
        await cmd.ExecuteNonQueryAsync(ct).ConfigureAwait(false);
        await tx.CommitAsync(ct).ConfigureAwait(false);
        return id;
    }

    public async Task<IReadOnlyList<ChatMessage>> ListMessagesAsync(string tenant, string principal,
        string chatId, int limit=250, CancellationToken ct=default)
    {
        if(limit<1 || limit>1000) throw new ArgumentOutOfRangeException(nameof(limit));
        await using var db=await OpenAsync(ct).ConfigureAwait(false);
        await EnsureOwnedAsync(db,null,tenant,principal,chatId,ct).ConfigureAwait(false);
        await using var cmd=db.CreateCommand();
        cmd.CommandText=@"SELECT m.id,m.role,m.content,m.created_utc FROM messages m
JOIN chats c ON c.id=m.chat_id
WHERE c.id=$chat AND c.tenant=$tenant AND c.owner=$owner
ORDER BY m.created_utc DESC,m.id DESC LIMIT $limit;";
        Scope(cmd,tenant,principal,chatId);
        cmd.Parameters.AddWithValue("$limit",limit);
        var result=new List<ChatMessage>();
        await using var reader=await cmd.ExecuteReaderAsync(ct).ConfigureAwait(false);
        while(await reader.ReadAsync(ct).ConfigureAwait(false))
            result.Add(new ChatMessage(reader.GetString(0),reader.GetString(1),
                reader.GetString(2),reader.GetString(3)));
        result.Reverse();
        return result;
    }

    public async Task<StoredAttachment> RegisterAttachmentAsync(string tenant,string principal,
        string chatId,string storageId,string sha256,string mime,long bytes,CancellationToken ct=default)
    {
        if(bytes<=0 || bytes>MaxFileBytes)throw new ArgumentOutOfRangeException(nameof(bytes));
        if(!Guid.TryParseExact(storageId,"N",out _))throw new ArgumentException("Invalid opaque ID.");
        if(sha256.Length!=64 || !System.Text.RegularExpressions.Regex.IsMatch(sha256,"^[0-9a-f]{64}$"))
            throw new ArgumentException("SHA-256 must be lowercase hexadecimal.");
        await using var db=await OpenAsync(ct).ConfigureAwait(false);
        await using var tx=(SqliteTransaction)await db.BeginTransactionAsync(ct).ConfigureAwait(false);
        await EnsureOwnedAsync(db,tx,tenant,principal,chatId,ct).ConfigureAwait(false);
        await using(var quota=db.CreateCommand())
        {
            quota.Transaction=tx;
            quota.CommandText="SELECT COALESCE(SUM(size_bytes),0) FROM attachments WHERE chat_id=$chat;";
            quota.Parameters.AddWithValue("$chat",chatId);
            var current=Convert.ToInt64(await quota.ExecuteScalarAsync(ct).ConfigureAwait(false));
            if(current>MaxChatBytes-bytes)throw new InvalidOperationException("Chat attachment quota exceeded.");
        }
        var id=Guid.NewGuid().ToString("N");
        await using(var insert=db.CreateCommand())
        {
            insert.Transaction=tx;
            insert.CommandText=@"INSERT INTO attachments(id,chat_id,storage_id,sha256,mime,size_bytes,created_utc)
VALUES($id,$chat,$storage,$sha,$mime,$bytes,$at);";
            insert.Parameters.AddRange(new[]{P("$id",id),P("$chat",chatId),P("$storage",storageId),
                P("$sha",sha256),P("$mime",mime),P("$bytes",bytes),
                P("$at",DateTimeOffset.UtcNow.ToString("O"))});
            await insert.ExecuteNonQueryAsync(ct).ConfigureAwait(false);
        }
        await tx.CommitAsync(ct).ConfigureAwait(false);
        return new StoredAttachment(id,storageId,sha256,mime,bytes);
    }

    public async Task<StoredAttachment> GetAttachmentAsync(string tenant,string principal,
        string chatId,string id,CancellationToken ct=default)
    {
        await using var db=await OpenAsync(ct).ConfigureAwait(false);
        await using var cmd=db.CreateCommand();
        cmd.CommandText=@"SELECT a.id,a.storage_id,a.sha256,a.mime,a.size_bytes FROM attachments a
JOIN chats c ON c.id=a.chat_id
WHERE a.id=$id AND c.id=$chat AND c.tenant=$tenant AND c.owner=$owner;";
        Scope(cmd,tenant,principal,chatId);
        cmd.Parameters.AddWithValue("$id",Required(id,nameof(id)));
        await using var reader=await cmd.ExecuteReaderAsync(ct).ConfigureAwait(false);
        if(!await reader.ReadAsync(ct).ConfigureAwait(false))
            throw new UnauthorizedAccessException("Attachment not available.");
        return new StoredAttachment(reader.GetString(0),reader.GetString(1),
            reader.GetString(2),reader.GetString(3),reader.GetInt64(4));
    }

    public async Task<int> PruneMessagesAsync(string tenant,string principal,string chatId,
        DateTimeOffset before,CancellationToken ct=default)
    {
        await using var db=await OpenAsync(ct).ConfigureAwait(false);
        await using var tx=(SqliteTransaction)await db.BeginTransactionAsync(ct).ConfigureAwait(false);
        await EnsureOwnedAsync(db,tx,tenant,principal,chatId,ct).ConfigureAwait(false);
        await using var cmd=db.CreateCommand();
        cmd.Transaction=tx;
        cmd.CommandText="DELETE FROM messages WHERE chat_id=$chat AND created_utc<$before;";
        cmd.Parameters.AddWithValue("$chat",chatId);
        cmd.Parameters.AddWithValue("$before",before.UtcDateTime.ToString("O"));
        var count=await cmd.ExecuteNonQueryAsync(ct).ConfigureAwait(false);
        await tx.CommitAsync(ct).ConfigureAwait(false);
        return count;
    }

    // Returns physical storage IDs for subsequent safe removal by owned attachment store.
    // A crash between DB commit and physical purge requires orphan-file reconciliation.
    public async Task<ChatDeleteReceipt> DeleteChatAsync(string tenant,string principal,
        string chatId,CancellationToken ct=default)
    {
        await using var db=await OpenAsync(ct).ConfigureAwait(false);
        await using var tx=(SqliteTransaction)await db.BeginTransactionAsync(ct).ConfigureAwait(false);
        await EnsureOwnedAsync(db,tx,tenant,principal,chatId,ct).ConfigureAwait(false);
        var ids=new List<string>();
        await using(var fetch=db.CreateCommand())
        {
            fetch.Transaction=tx;
            fetch.CommandText="SELECT storage_id FROM attachments WHERE chat_id=$chat;";
            fetch.Parameters.AddWithValue("$chat",chatId);
            await using var rd=await fetch.ExecuteReaderAsync(ct).ConfigureAwait(false);
            while(await rd.ReadAsync(ct).ConfigureAwait(false)) ids.Add(rd.GetString(0));
        }
        await using(var remove=db.CreateCommand())
        {
            remove.Transaction=tx;
            remove.CommandText="DELETE FROM chats WHERE id=$chat AND tenant=$tenant AND owner=$owner;";
            Scope(remove,tenant,principal,chatId);
            if(await remove.ExecuteNonQueryAsync(ct).ConfigureAwait(false)!=1)
                throw new UnauthorizedAccessException("Chat not owned.");
        }
        await tx.CommitAsync(ct).ConfigureAwait(false);
        return new ChatDeleteReceipt(chatId,ids);
    }
}
