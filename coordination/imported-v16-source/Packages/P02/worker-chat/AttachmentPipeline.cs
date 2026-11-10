// NOX V16 P02 — file picker -> native stream -> staging -> SHA-256 -> STORED-ID.
// No HTML rendering, executable MIME, remote URL fetching or privilege-bearing WebView bridge.
using System;
using System.IO;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.P02;

public sealed record AttachmentAck(string StoredId, string Sha256, string Mime, long Bytes, string StorageId);

public sealed class AttachmentPipeline
{
    private readonly ChatSqliteStore _db;
    private readonly string _staging;
    private readonly string _stored;
    private readonly SemaphoreSlim _stagingGate = new(1, 1);

    public AttachmentPipeline(ChatSqliteStore database, string appOwnedRoot)
    {
        _db=database ?? throw new ArgumentNullException(nameof(database));
        if (string.IsNullOrWhiteSpace(appOwnedRoot)) throw new ArgumentException("App-owned root required.");
        var root=Path.GetFullPath(appOwnedRoot);
        _staging=Path.Combine(root,"staging");
        _stored=Path.Combine(root,"stored");
        Directory.CreateDirectory(_staging);
        Directory.CreateDirectory(_stored);
    }

    private static string ValidateMime(string mime) => mime switch
    {
        "application/pdf" => mime,
        "image/png" => mime,
        "image/jpeg" => mime,
        "text/plain" => mime,
        _ => throw new InvalidDataException("Unsupported attachment media type.")
    };

    private static void CheckSignature(ReadOnlySpan<byte> start,string mime)
    {
        var good=mime switch
        {
            "application/pdf" => start.Length>=5 &&
                start[0]=='%' && start[1]=='P' && start[2]=='D' && start[3]=='F' && start[4]=='-',
            "image/png" => start.Length>=8 &&
                start[0]==137 && start[1]==80 && start[2]==78 && start[3]==71 &&
                start[4]==13 && start[5]==10 && start[6]==26 && start[7]==10,
            "image/jpeg" => start.Length>=3 &&
                start[0]==0xff && start[1]==0xd8 && start[2]==0xff,
            "text/plain" => start.Length>0 && start.IndexOf((byte)0)==-1,
            _ => false
        };
        if(!good) throw new InvalidDataException("Media signature disagrees with requested MIME.");
    }

    /// <summary>Caller identity must be issued by native host, not JavaScript.
    /// Returns ACK only after the content has been flushed and SQLite transaction committed.
    /// Crash recovery must garbage-collect unregistered app-owned blobs after a safe grace period.
    /// </summary>
    public async Task<AttachmentAck> StoreAsync(
        string tenant,string principal,string chatId,Stream input,string requestedMime,
        CancellationToken ct=default)
    {
        if(input is null || !input.CanRead)throw new ArgumentException("Readable upload stream required.");
        var mime=ValidateMime(requestedMime);
        var storageId=Guid.NewGuid().ToString("N");
        var staged=Path.Combine(_staging,storageId+".tmp");
        var stored=Path.Combine(_stored,storageId+".blob");
        var moved=false;
        await _stagingGate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            long total=0;
            byte[] prefix=new byte[12];
            var prefixLen=0;
            using var hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            await using(var output=new FileStream(staged,FileMode.CreateNew,FileAccess.Write,
                FileShare.None,64*1024,FileOptions.Asynchronous | FileOptions.SequentialScan))
            {
                var buffer=new byte[64*1024];
                int n;
                while((n=await input.ReadAsync(buffer.AsMemory(),ct).ConfigureAwait(false))>0)
                {
                    if(n>ChatSqliteStore.MaxFileBytes-total)
                        throw new InvalidDataException("Attachment exceeds per-file quota.");
                    if(prefixLen<prefix.Length)
                    {
                        var take=Math.Min(n,prefix.Length-prefixLen);
                        Array.Copy(buffer,0,prefix,prefixLen,take);
                        prefixLen+=take;
                    }
                    hash.AppendData(buffer.AsSpan(0,n));
                    await output.WriteAsync(buffer.AsMemory(0,n),ct).ConfigureAwait(false);
                    total+=n;
                }
                await output.FlushAsync(ct).ConfigureAwait(false);
                output.Flush(flushToDisk:true);
            }
            if(total==0)throw new InvalidDataException("Empty attachment rejected.");
            CheckSignature(prefix.AsSpan(0,prefixLen),mime);
            var sha=Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
            File.Move(staged,stored);
            moved=true;
            var record=await _db.RegisterAttachmentAsync(tenant,principal,chatId,storageId,
                sha,mime,total,ct).ConfigureAwait(false);
            return new AttachmentAck(record.Id,record.Sha256,record.Mime,record.Bytes,record.StorageId);
        }
        catch
        {
            // Never leave failed validation or aborted writes as visible attachment IDs.
            if(File.Exists(staged)) File.Delete(staged);
            if(moved && File.Exists(stored)) File.Delete(stored);
            throw;
        }
        finally { _stagingGate.Release(); }
    }

    /// <summary>Native-only source for chat/RAG, gated by DB owner+tenant and reverified SHA.
    /// The returned stream is caller-owned; never pass its file path into browser DOM.</summary>
    public async Task<Stream> OpenAuthorizedAsync(string tenant,string principal,
        string chatId,string attachmentId,CancellationToken ct=default)
    {
        var item=await _db.GetAttachmentAsync(tenant,principal,chatId,attachmentId,ct)
            .ConfigureAwait(false);
        if(!Guid.TryParseExact(item.StorageId,"N",out _))
            throw new InvalidDataException("Invalid stored file identity.");
        var path=Path.Combine(_stored,item.StorageId+".blob");
        if((File.GetAttributes(path) & FileAttributes.ReparsePoint)!=0)
            throw new IOException("Symlinked stored blobs are forbidden.");
        var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read,
            64*1024,FileOptions.Asynchronous | FileOptions.SequentialScan);
        try
        {
            if(stream.Length!=item.Bytes)throw new InvalidDataException("Stored file size changed.");
            var digest=await SHA256.HashDataAsync(stream,ct).ConfigureAwait(false);
            if(!CryptographicOperations.FixedTimeEquals(digest,Convert.FromHexString(item.Sha256)))
                throw new InvalidDataException("Stored file checksum mismatch.");
            stream.Position=0;
            return stream;
        }
        catch { await stream.DisposeAsync().ConfigureAwait(false); throw; }
    }

    /// <summary>Only invoke with DB-issued ChatDeleteReceipt from the same trusted host.
    /// This removes application-owned bytes, not guaranteed secure erasure on SSDs.</summary>
    public void PurgeDeletedChatFiles(ChatDeleteReceipt receipt)
    {
        if(receipt is null)throw new ArgumentNullException(nameof(receipt));
        foreach(var id in receipt.StorageIds)
        {
            if(!Guid.TryParseExact(id,"N",out _))
                throw new InvalidDataException("Invalid deletion receipt storage ID.");
            var path=Path.Combine(_stored,id+".blob");
            if(!File.Exists(path))continue;
            if((File.GetAttributes(path) & FileAttributes.ReparsePoint)!=0)
                throw new IOException("Symlinked stored blob refused.");
            File.Delete(path);
        }
    }
}
