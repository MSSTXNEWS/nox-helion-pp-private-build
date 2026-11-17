"""Bounded authenticated ciphertext transport; source metadata stays encrypted.

No native invocation on import. Private key is local-only; source files remain
unchanged. Exact CP55 and S03 selection is delegated to pinned owner scope.
"""
import base64, hashlib, io, json, os, re, sqlite3, stat, struct, time
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC=b'NOXCP55E'; BLOCK=1024*1024; MAX_TOTAL=2*1024**3
MAX_MANIFEST=1024*1024; PART_BYTES=80*1024**2
LABEL=b'NOX_CP55_S03_STOP_BACKUP_V1'
def require(ok,code):
    if not ok: raise RuntimeError('HOLD_CP55_'+code)
def canonical(obj): return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def exact(stream,n):
    chunks=[]
    while n:
        part=stream.read(min(n,BLOCK));require(bool(part),'TRUNCATED');chunks.append(part);n-=len(part)
    return b''.join(chunks)
def safe(path):
    p=Path(path).absolute();require(not any(x.is_symlink() for x in (p,*p.parents)),'SYMLINK');return p
def private_write(path,raw):
    path=safe(path);require(path.parent.is_dir() and not path.parent.stat().st_mode&0o077,'PRIVATE_PARENT')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def prepare(directory,scope_sha):
    require(re.fullmatch('[a-f0-9]{64}',scope_sha) is not None,'SCOPE_SHA')
    directory=safe(directory);directory.mkdir(mode=0o700)
    key=rsa.generate_private_key(public_exponent=65537,key_size=4096)
    pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    public={'schema':'NOX_CP55_S03_RECIPIENT_V1','public_key_pem':pem.decode(),'key_id':sha(pem),
            'scope_sha256':scope_sha,'transfer_id':os.urandom(16).hex(),'created_at':int(time.time()),'expires_at':int(time.time())+7200}
    private_write(directory/'private.pem',key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    private_write(directory/'public.json',canonical(public)+b'\n')
    return {'key_id':public['key_id'],'public_metadata_sha256':sha(canonical(public)),'private_key_exported':False}
def public_key(public,scope_sha):
    require(public.get('schema')=='NOX_CP55_S03_RECIPIENT_V1' and public.get('scope_sha256')==scope_sha,'PUBLIC_SCOPE')
    require(type(public.get('expires_at')) is int and type(public.get('created_at')) is int and
            0<public['expires_at']-public['created_at']<=7200 and public['created_at']-5<=time.time()<public['expires_at'],'KEY_TTL')
    pem=public['public_key_pem'].encode();require(sha(pem)==public['key_id'],'KEY_ID')
    key=serialization.load_pem_public_key(pem)
    require(isinstance(key,rsa.RSAPublicKey) and key.key_size==4096 and key.public_numbers().e==65537,'RSA4096')
    return key
def identity(p):
    st=p.stat();return(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
def file_sha(p,guard):
    p=safe(p);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd);require(stat.S_ISREG(st.st_mode),'REGULAR_FILE');h=hashlib.sha256();n=0
        while True:
            guard();block=os.read(fd,BLOCK)
            if not block:break
            h.update(block);n+=len(block);require(n<=MAX_TOTAL,'FILE_SIZE')
        require(n==st.st_size and identity(p)==(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns),'FILE_CHANGED')
        return h.hexdigest(),n
    finally:os.close(fd)
def seal(rows,public,scope_sha,source,request,out,guard):
    key=public_key(public,scope_sha)
    require(callable(guard) and re.fullmatch('[a-f0-9]{40}',source) and re.fullmatch('[0-9]{1,24}',request),'CONTEXT')
    files=[];seen=set();before=[]
    for path,name,expected in rows:
        path=safe(path);require(re.fullmatch(r'(?:checkpoint55/)?[A-Za-z0-9_.-]+',name) and name not in seen,'FILE_NAME');seen.add(name)
        before.append(identity(path));digest,n=file_sha(path,guard)
        require(expected is None or expected==digest,'PINNED_FILE_SHA')
        files.append({'name':name,'bytes':n,'sha256':digest})
    total=sum(x['bytes'] for x in files);require(0<total<=MAX_TOTAL and 1<=len(files)<=32,'TOTAL')
    manifest=canonical({'schema':'NOX_CP55_S03_PRIVATE_MANIFEST_V1','source':source,'request':request,'files':files,
                        'scope_sha256':scope_sha,'warm_weights_included':False,'training_resume_tested':False})
    require(len(manifest)<=MAX_MANIFEST,'MANIFEST_BOUND')
    aes=os.urandom(32);nonce=os.urandom(12)
    header={'schema':'NOX_CP55_S03_CIPHER_V1','key_id':public['key_id'],'transfer_id':public['transfer_id'],
            'scope_sha256':scope_sha,'source':source,'request':request,'plaintext_bytes':4+len(manifest)+total,
            'nonce':base64.b64encode(nonce).decode(),'wrapped_key':base64.b64encode(key.encrypt(aes,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=LABEL))).decode()}
    raw=canonical(header);prefix=MAGIC+struct.pack('>I',len(raw))+raw
    enc=Cipher(algorithms.AES(aes),modes.GCM(nonce)).encryptor();enc.authenticate_additional_data(prefix)
    out.write(prefix);out.write(enc.update(struct.pack('>I',len(manifest))+manifest))
    for (path,_,_),row,original in zip(rows,files,before):
        h=hashlib.sha256();n=0
        with safe(path).open('rb') as f:
            while True:
                guard();block=f.read(BLOCK)
                if not block:break
                h.update(block);n+=len(block);require(n<=row['bytes'],'FILE_GREW');out.write(enc.update(block))
        require(n==row['bytes'] and h.hexdigest()==row['sha256'] and identity(Path(path))==original,'FILE_CHANGED')
    # Recheck every source before emitting the authenticating tag.
    for (path,_,_),row,original in zip(rows,files,before):
        digest,n=file_sha(path,guard);require(digest==row['sha256'] and n==row['bytes'] and identity(Path(path))==original,'SOURCE_FINAL_SHA')
    guard();out.write(enc.finalize());out.write(enc.tag);out.flush()
    return {'files':len(files),'source_bytes':total,'source_deleted':False,'warm_weights_transferred':False}

class Parts:
    def __init__(self,directory):
        self.directory=safe(directory);self.directory.mkdir(mode=0o700);self.rows=[];self.f=None;self.total=0;self.digest=hashlib.sha256()
    def write(self,raw):
        self.total+=len(raw);require(self.total<=MAX_TOTAL+MAX_MANIFEST+65536,'CIPHER_BOUND');self.digest.update(raw)
        while raw:
            if self.f is None:
                self.name=f'cp55-s03.cipher.part{len(self.rows):03d}';self.n=0;self.h=hashlib.sha256()
                self.f=os.fdopen(os.open(self.directory/self.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb')
            part,raw=raw[:PART_BYTES-self.n],raw[PART_BYTES-self.n:];self.f.write(part);self.h.update(part);self.n+=len(part)
            if self.n==PART_BYTES:self.close_part()
    def close_part(self):
        if self.f:
            self.f.flush();os.fsync(self.f.fileno());self.f.close();self.f=None
            self.rows.append({'name':self.name,'bytes':self.n,'sha256':self.h.hexdigest()})
    def flush(self):
        if self.f:self.f.flush()
    def finish(self):
        self.close_part();result={'schema':'NOX_CP55_CIPHER_PARTS_V1','parts':self.rows,'bytes':self.total,'sha256':self.digest.hexdigest()}
        private_write(self.directory/'CIPHER_PARTS.json',canonical(result)+b'\n');return result

class PartReader:
    def __init__(self,directory,receipt):self.directory=safe(directory);self.rows=iter(receipt['parts']);self.f=None;self.h=None;self.n=0;self.total=0;self.digest=hashlib.sha256();self.receipt=receipt;self.seen=set()
    def __del__(self):
        if self.f is not None:self.f.close()
    def read(self,n):
        require(0<=n<=BLOCK,'READ_BOUND');result=bytearray()
        while len(result)<n:
            if self.f is None:
                row=next(self.rows,None)
                if row is None:
                    require(self.total==self.receipt['bytes'] and self.digest.hexdigest()==self.receipt['sha256'],'FULL_CIPHER_SHA');break
                require(re.fullmatch(r'cp55-s03\.cipher\.part[0-9]{3}',row['name']) and row['name'] not in self.seen,'PART_NAME');self.seen.add(row['name'])
                self.row=row;self.f=safe(self.directory/row['name']).open('rb');self.h=hashlib.sha256();self.n=0
            block=self.f.read(n-len(result))
            if block:
                self.h.update(block);self.digest.update(block);self.n+=len(block);self.total+=len(block);result.extend(block)
                require(self.n<=self.row['bytes'] and self.total<=MAX_TOTAL+MAX_MANIFEST+65536,'PART_BOUND')
            else:
                self.f.close();self.f=None;require(self.n==self.row['bytes'] and self.h.hexdigest()==self.row['sha256'],'PART_SHA')
        return bytes(result)

def decrypt_chunks(directory,receipt,public,key,source,request):
    reader=PartReader(directory,receipt);prefix=exact(reader,12);require(prefix[:8]==MAGIC,'MAGIC');n=struct.unpack('>I',prefix[8:])[0];require(0<n<8192,'HEADER_SIZE')
    raw=exact(reader,n);prefix+=raw;header=json.loads(raw)
    require(header.get('schema')=='NOX_CP55_S03_CIPHER_V1' and header['key_id']==public['key_id'] and header['transfer_id']==public['transfer_id'] and header['scope_sha256']==public['scope_sha256'] and header['source']==source and header['request']==request,'HEADER_BINDING')
    count=header['plaintext_bytes'];require(type(count) is int and 0<count<=MAX_TOTAL+MAX_MANIFEST+4,'PLAIN_BOUND')
    aes=key.decrypt(base64.b64decode(header['wrapped_key'],validate=True),padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=LABEL))
    dec=Cipher(algorithms.AES(aes),modes.GCM(base64.b64decode(header['nonce'],validate=True))).decryptor();dec.authenticate_additional_data(prefix)
    while count:
        raw=exact(reader,min(BLOCK,count));count-=len(raw);yield dec.update(raw)
    dec.finalize_with_tag(exact(reader,16));require(reader.read(1)==b'','TRAILING_BYTES')

class ChunkReader:
    def __init__(self,chunks):self.chunks=iter(chunks);self.pending=b''
    def read(self,n):
        require(n<=BLOCK,'READ_BOUND');out=bytearray()
        while len(out)<n:
            if not self.pending:self.pending=next(self.chunks,b'')
            if not self.pending:break
            part,self.pending=self.pending[:n-len(out)],self.pending[n-len(out):];out.extend(part)
        return bytes(out)

def restore(directory,private_dir,destination,source,request):
    private_dir=safe(private_dir);p=safe(private_dir/'private.pem');st=p.stat()
    require(st.st_uid==os.geteuid() and stat.S_IMODE(st.st_mode)==0o600,'PRIVATE_KEY_MODE')
    public=json.loads((private_dir/'public.json').read_bytes());key=serialization.load_pem_private_key(p.read_bytes(),None)
    require(sha(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))==public['key_id'],'PRIVATE_KEY_MATCH')
    receipt=json.loads(safe(Path(directory)/'CIPHER_PARTS.json').read_bytes())
    # Authenticate whole ciphertext FIRST, before writing/decode of private data.
    for block in decrypt_chunks(directory,receipt,public,key,source,request):pass
    destination=safe(destination);destination.mkdir(mode=0o700)
    reader=ChunkReader(decrypt_chunks(directory,receipt,public,key,source,request));n=struct.unpack('>I',exact(reader,4))[0];require(n<=MAX_MANIFEST,'MANIFEST_SIZE')
    manifest=json.loads(exact(reader,n));require(manifest['source']==source and manifest['request']==request and manifest['scope_sha256']==public['scope_sha256'],'MANIFEST_BINDING')
    seen=set();total=0
    for row in manifest['files']:
        name=row['name'];require(re.fullmatch(r'(?:checkpoint55/)?[A-Za-z0-9_.-]+',name) and name not in seen,'RESTORE_NAME');seen.add(name)
        count=row['bytes'];require(type(count) is int and 0<=count<=MAX_TOTAL,'RESTORE_BOUND');total+=count;require(total<=MAX_TOTAL,'RESTORE_TOTAL')
        path=destination/name;path.parent.mkdir(mode=0o700,exist_ok=True);h=hashlib.sha256()
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:
            while count:
                raw=exact(reader,min(BLOCK,count));count-=len(raw);h.update(raw);f.write(raw)
            f.flush();os.fsync(f.fileno())
        require(h.hexdigest()==row['sha256'],'RESTORED_SHA')
    require(reader.read(1)==b'','PLAINTEXT_TRAILING')
    require('s03.sqlite' in seen,'S03_REQUIRED')
    with sqlite3.connect((destination/'s03.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        require(db.execute('PRAGMA quick_check').fetchall()==[('ok',)],'S03_QUICK_CHECK')
    result={'schema':'NOX_CP55_S03_LOCAL_RESTORE_V1','source':source,'request':request,'files':manifest['files'],
            'ciphertext_sha256':receipt['sha256'],'sqlite_quick_check':True,'checkpoint_byte_restore':True,
            'training_resume_tested':False,'warm_weights_transferred':False,'drive_copy_verified':False,'cleanup_authorized':False}
    private_write(destination/'RESTORE_VERIFIED.json',canonical(result)+b'\n');return result
