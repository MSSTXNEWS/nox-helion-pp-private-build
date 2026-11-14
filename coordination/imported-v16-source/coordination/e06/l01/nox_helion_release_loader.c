/* NOX HELION · L01 secure Micro Loader, based on existing Windows x64 loader.
   One downloader, no second installer/DB/LLM. Owner #1 final integration.
   CAVEAT: no trusted manifest/Setup is published yet. An unconfigured binary
   FAILS CLOSED. Set NOX_PINNED_MANIFEST_SHA256_HEX only in approved release build.
   Raw five-line V2 manifest MUST match the SHA256 hard-pinned inside this EXE.
   No code runs until manifest, HTTPS transfer, byte count and SHA all match.
*/
#include "nox_loader_policy.h"

typedef unsigned char BYTE;
typedef unsigned short WCHAR;
typedef unsigned int DWORD; /* 32-bit even on LP64 hosts */
typedef unsigned int ULONG;
typedef int BOOL;
typedef int HRESULT;
typedef int NTSTATUS;
typedef unsigned long long SIZE_T;
typedef void *HANDLE;
typedef HANDLE HINTERNET;
typedef HANDLE HWND;
typedef HANDLE HINSTANCE;
typedef const WCHAR *PCWSTR;
typedef WCHAR *PWSTR;
typedef BYTE *PUCHAR;
typedef ULONG *PULONG;
#define WINAPI __stdcall
#define INVALID_HANDLE_VALUE ((HANDLE)(SIZE_T)(-1))
#define GENERIC_READ 0x80000000u
#define GENERIC_WRITE 0x40000000u
#define FILE_SHARE_READ 1u
#define OPEN_EXISTING 3u
#define FILE_ATTRIBUTE_NORMAL 0x80u
#define MB_OK 0u
#define MB_OKCANCEL 1u
#define MB_ICONERROR 0x10u
#define MB_ICONINFORMATION 0x40u
#define IDOK 1
#define MAX_PATH_W 768
#define WINHTTP_FLAG_SECURE 0x00800000u
#define WINHTTP_OPTION_DISABLE_FEATURE 63u
#define WINHTTP_DISABLE_REDIRECTS 2u
#define WINHTTP_DISABLE_COOKIES 1u
#define WINHTTP_DISABLE_AUTHENTICATION 4u
#define WINHTTP_QUERY_STATUS_CODE 19u
#define WINHTTP_QUERY_LOCATION 33u
#define WINHTTP_QUERY_FLAG_NUMBER 0x20000000u
#define HKEY_CURRENT_USER ((HANDLE)(SIZE_T)0x80000001u)
#define RRF_RT_REG_DWORD 0x18u
#define REG_DWORD 4u
#define MOVEFILE_REPLACE_EXISTING 1u
#define MOVEFILE_WRITE_THROUGH 8u

__declspec(dllimport) void WINAPI ExitProcess(DWORD);
__declspec(dllimport) DWORD WINAPI GetModuleFileNameW(HINSTANCE,PWSTR,DWORD);
__declspec(dllimport) DWORD WINAPI GetTempPathW(DWORD,PWSTR);
__declspec(dllimport) DWORD WINAPI GetTempFileNameW(PCWSTR,PCWSTR,DWORD,PWSTR);
__declspec(dllimport) HANDLE WINAPI GetProcessHeap(void);
__declspec(dllimport) void* WINAPI HeapAlloc(HANDLE,DWORD,SIZE_T);
__declspec(dllimport) BOOL WINAPI HeapFree(HANDLE,DWORD,void*);
__declspec(dllimport) HANDLE WINAPI CreateFileW(PCWSTR,DWORD,DWORD,void*,DWORD,DWORD,HANDLE);
__declspec(dllimport) BOOL WINAPI ReadFile(HANDLE,void*,DWORD,DWORD*,void*);
__declspec(dllimport) BOOL WINAPI WriteFile(HANDLE,const void*,DWORD,DWORD*,void*);
__declspec(dllimport) BOOL WINAPI CloseHandle(HANDLE);
__declspec(dllimport) BOOL WINAPI DeleteFileW(PCWSTR);
__declspec(dllimport) BOOL WINAPI MoveFileExW(PCWSTR,PCWSTR,DWORD);
__declspec(dllimport) BOOL WINAPI FlushFileBuffers(HANDLE);
__declspec(dllimport) int WINAPI MessageBoxW(HWND,PCWSTR,PCWSTR,unsigned int);
__declspec(dllimport) HINSTANCE WINAPI ShellExecuteW(HWND,PCWSTR,PCWSTR,PCWSTR,PCWSTR,int);
__declspec(dllimport) NTSTATUS WINAPI BCryptOpenAlgorithmProvider(HANDLE*,PCWSTR,PCWSTR,ULONG);
__declspec(dllimport) NTSTATUS WINAPI BCryptGetProperty(HANDLE,PCWSTR,PUCHAR,ULONG,PULONG,ULONG);
__declspec(dllimport) NTSTATUS WINAPI BCryptCreateHash(HANDLE,HANDLE*,PUCHAR,ULONG,PUCHAR,ULONG,ULONG);
__declspec(dllimport) NTSTATUS WINAPI BCryptHashData(HANDLE,PUCHAR,ULONG,ULONG);
__declspec(dllimport) NTSTATUS WINAPI BCryptFinishHash(HANDLE,PUCHAR,ULONG,ULONG);
__declspec(dllimport) NTSTATUS WINAPI BCryptDestroyHash(HANDLE);
__declspec(dllimport) NTSTATUS WINAPI BCryptCloseAlgorithmProvider(HANDLE,ULONG);
__declspec(dllimport) HINTERNET WINAPI WinHttpOpen(PCWSTR,DWORD,PCWSTR,PCWSTR,DWORD);
__declspec(dllimport) HINTERNET WINAPI WinHttpConnect(HINTERNET,PCWSTR,unsigned short,DWORD);
__declspec(dllimport) HINTERNET WINAPI WinHttpOpenRequest(HINTERNET,PCWSTR,PCWSTR,PCWSTR,PCWSTR,PCWSTR*,DWORD);
__declspec(dllimport) BOOL WINAPI WinHttpSetTimeouts(HINTERNET,int,int,int,int);
__declspec(dllimport) BOOL WINAPI WinHttpSetOption(HINTERNET,DWORD,void*,DWORD);
__declspec(dllimport) BOOL WINAPI WinHttpSendRequest(HINTERNET,PCWSTR,DWORD,void*,DWORD,DWORD,SIZE_T);
__declspec(dllimport) BOOL WINAPI WinHttpReceiveResponse(HINTERNET,void*);
__declspec(dllimport) BOOL WINAPI WinHttpQueryHeaders(HINTERNET,DWORD,PCWSTR,void*,DWORD*,DWORD*);
__declspec(dllimport) BOOL WINAPI WinHttpReadData(HINTERNET,void*,DWORD,DWORD*);
__declspec(dllimport) BOOL WINAPI WinHttpCloseHandle(HINTERNET);
__declspec(dllimport) DWORD WINAPI RegGetValueW(HANDLE,PCWSTR,PCWSTR,DWORD,DWORD*,void*,DWORD*);
__declspec(dllimport) DWORD WINAPI RegSetKeyValueW(HANDLE,PCWSTR,PCWSTR,DWORD,const void*,DWORD);

#ifndef NOX_PINNED_MANIFEST_SHA256_HEX
#define NOX_PINNED_MANIFEST_SHA256_HEX "0000000000000000000000000000000000000000000000000000000000000000"
#endif
#ifndef NOX_MIN_BOOTSTRAP_VERSION
#define NOX_MIN_BOOTSTRAP_VERSION 1u
#endif

static const WCHAR TITLE[]=L"NOX HELION | Verified Bootstrap";
static const WCHAR HASHALG[]=L"SHA256";
static const WCHAR OBJECTLEN[]=L"ObjectLength";
static const WCHAR CONFIG[]=L"NOX-HELION-RELEASE.txt";
static const WCHAR REGISTER[]=L"Software\\NOX_HELION\\Bootstrap";
static const WCHAR HIGHEST[]=L"HighestVersion";
static const WCHAR HTTPAGENT[]=L"NOX-HELION-L01/1.0";
static const WCHAR GETMETHOD[]=L"GET";
static const WCHAR HTTPS[]=L"https://";

static unsigned int wlen(const WCHAR*s){unsigned int i=0;while(s[i])i++;return i;}
static int wappend(WCHAR*d,unsigned int cap,const WCHAR*s){unsigned int n=wlen(d),i=0;while(s[i]){if(n+i+1>=cap)return 0;d[n+i]=s[i];i++;}d[n+i]=0;return 1;}
static int wfrom(const char*s,WCHAR*out,unsigned int cap){unsigned int i=0;while(s[i]){if(i+1>=cap || (unsigned char)s[i]<32 || (unsigned char)s[i]>126)return 0;out[i]=(WCHAR)(unsigned char)s[i];i++;}out[i]=0;return 1;}
static int afrom(const WCHAR*s,char*out,unsigned int cap){unsigned int i=0;while(s[i]){if(i+1>=cap||s[i]<32||s[i]>126)return 0;out[i]=(char)s[i];i++;}out[i]=0;return 1;}
static void say(PCWSTR msg,unsigned int flags){MessageBoxW(0,msg,TITLE,flags);}

static int digest_equal(const BYTE*a,const BYTE*b,unsigned int n){unsigned int i;unsigned int bad=0;for(i=0;i<n;i++)bad |= (unsigned int)(a[i]^b[i]);return bad==0;}

/* The hash callback is incremental and handles zero-byte input. */
typedef struct { HANDLE alg,hash,heap; void *object; } Hash;
static int hash_open(Hash*h){ULONG objectlen=0,got=0;
    h->alg=0;h->hash=0;h->object=0;h->heap=GetProcessHeap();
    if(BCryptOpenAlgorithmProvider(&h->alg,HASHALG,0,0)<0)return 0;
    if(BCryptGetProperty(h->alg,OBJECTLEN,(PUCHAR)&objectlen,sizeof(objectlen),&got,0)<0||objectlen<16||objectlen>65536)return 0;
    h->object=HeapAlloc(h->heap,0,objectlen);if(!h->object)return 0;
    if(BCryptCreateHash(h->alg,&h->hash,(PUCHAR)h->object,objectlen,0,0,0)<0)return 0;
    return 1;
}
static int hash_feed(Hash*h,const void*buf,DWORD n){return BCryptHashData(h->hash,(PUCHAR)buf,n,0)>=0;}
static int hash_finish(Hash*h,BYTE out[32]){return BCryptFinishHash(h->hash,out,32,0)>=0;}
static void hash_close(Hash*h){if(h->hash)BCryptDestroyHash(h->hash);if(h->object)HeapFree(h->heap,0,h->object);if(h->alg)BCryptCloseAlgorithmProvider(h->alg,0);}

static int hash_buf(const BYTE*b,DWORD n,BYTE out[32]){Hash h;int ok=0;
    if(hash_open(&h)){ok=hash_feed(&h,b,n)&&hash_finish(&h,out);}hash_close(&h);return ok;
}

/* Strict URL split: only ASCII HTTPS DNS hostname, no port/userinfo/IP/fragment.
   The full URL is independently authenticated by pinned-manifest SHA. */
static int split_url(const char*url,WCHAR*host,WCHAR*path,unsigned int hcap,unsigned int pcap){
    const char *s=url+8,*start=s;static char raw[2048];unsigned int i=0;
    if(!nox_url(url))return 0;
    while(*s && *s!='/')s++;
    if((unsigned int)(s-start)+1>sizeof(raw))return 0;
    while(start<s){raw[i++]=*start++;}raw[i]=0;
    if(!wfrom(raw,host,hcap))return 0;
    return wfrom(s,path,pcap);
}
static int same_host(const WCHAR*h,PCWSTR allowed){unsigned int i=0;while(h[i]&&allowed[i]){if(h[i]!=allowed[i])return 0;i++;}return h[i]==allowed[i];}
static int allowed_github_redirect(const char *old_url,const char *next_url){
    static WCHAR old_host[256],new_host[256],dummy[2048];
    if(!split_url(old_url,old_host,dummy,256,2048)||!split_url(next_url,new_host,dummy,256,2048))return 0;
    if(!same_host(old_host,L"github.com"))return 0;
    return same_host(new_host,L"release-assets.githubusercontent.com")||same_host(new_host,L"objects.githubusercontent.com");
}

static int https_download(const char*url,HANDLE output,unsigned long long maximum,Hash*hash,unsigned long long*written){
    HINTERNET session=0,conn=0,req=0;DWORD status=0,n=sizeof(status),idx=0;
    DWORD forbid=WINHTTP_DISABLE_REDIRECTS|WINHTTP_DISABLE_COOKIES|WINHTTP_DISABLE_AUTHENTICATION;
    static WCHAR host[256],path[2048];
    unsigned int redirects=0;
    static char current[2048];unsigned int k;
    int result=0;
    for(k=0;k<sizeof(current);k++){current[k]=url[k];if(!url[k])break;}
    if(k==sizeof(current))return 0;
    session=WinHttpOpen(HTTPAGENT,0,0,0,0);
    if(!session || !WinHttpSetTimeouts(session,10000,15000,30000,30000))goto finish;
    for(;;){
        if(!split_url(current,host,path,256,2048))goto finish;
        conn=WinHttpConnect(session,host,443,0);if(!conn)goto finish;
        req=WinHttpOpenRequest(conn,GETMETHOD,path,0,0,0,WINHTTP_FLAG_SECURE);
        if(!req||!WinHttpSetOption(req,WINHTTP_OPTION_DISABLE_FEATURE,&forbid,sizeof(forbid)))goto finish;
        if(!WinHttpSendRequest(req,0,0,0,0,0,0)||!WinHttpReceiveResponse(req,0))goto finish;
        n=sizeof(status);idx=0;
        if(!WinHttpQueryHeaders(req,WINHTTP_QUERY_STATUS_CODE|WINHTTP_QUERY_FLAG_NUMBER,0,&status,&n,&idx))goto finish;
        if(status==301||status==302||status==303||status==307||status==308){
            static WCHAR loc[2048];static char next[2048];
            n=sizeof(loc);idx=0;
            if(redirects++>0||!WinHttpQueryHeaders(req,WINHTTP_QUERY_LOCATION,0,loc,&n,&idx)||
               n<sizeof(WCHAR)||n>sizeof(loc)-sizeof(WCHAR))goto finish;
            loc[n/sizeof(WCHAR)]=0;
            if(!afrom(loc,next,sizeof(next))||!allowed_github_redirect(current,next))goto finish;
            for(k=0;k<sizeof(current);k++){current[k]=next[k];if(!next[k])break;}
            WinHttpCloseHandle(req);req=0;WinHttpCloseHandle(conn);conn=0;
            continue;
        }
        if(status!=200)goto finish;
        for(;;){
            static BYTE buffer[65536];DWORD got=0,wrote=0;
            if(!WinHttpReadData(req,buffer,sizeof(buffer),&got))goto finish;
            if(!got)break;
            if(*written>maximum || got>maximum-*written)goto finish;
            if(!WriteFile(output,buffer,got,&wrote,0)||wrote!=got||!hash_feed(hash,buffer,got))goto finish;
            *written+=got;
        }
        if(*written==maximum && FlushFileBuffers(output))result=1;
        goto finish;
    }
finish:
    if(req)WinHttpCloseHandle(req);
    if(conn)WinHttpCloseHandle(conn);
    if(session)WinHttpCloseHandle(session);
    return result;
}
static int remember_version(DWORD version){
    DWORD latest=0,sz=sizeof(latest),type=0;
    DWORD r=RegGetValueW(HKEY_CURRENT_USER,REGISTER,HIGHEST,RRF_RT_REG_DWORD,&type,&latest,&sz);
    if(r!=0 && r!=2)return 0; /* refuse uninspectable/invalid witness */
    if(r==0 && version<latest)return 0;
    if(r==0 && version==latest)return 1;
    return RegSetKeyValueW(HKEY_CURRENT_USER,REGISTER,HIGHEST,REG_DWORD,&version,sizeof(version))==0;
}
static int version_not_downgrade(DWORD version){
    DWORD latest=0,sz=sizeof(latest),type=0;
    DWORD r=RegGetValueW(HKEY_CURRENT_USER,REGISTER,HIGHEST,RRF_RT_REG_DWORD,&type,&latest,&sz);
    return (r==2)||(r==0 && version>=latest);
}
static int has_mz(PCWSTR path){HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,0,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,0);BYTE b[2];DWORD n=0;int ok=0;
    if(f==INVALID_HANDLE_VALUE)return 0;
    ok=ReadFile(f,b,2,&n,0)&&n==2&&b[0]=='M'&&b[1]=='Z';CloseHandle(f);return ok;
}
static int run(void){
    static WCHAR manifest_path[MAX_PATH_W],temp_dir[MAX_PATH_W],temp_path[MAX_PATH_W],exe_path[MAX_PATH_W];
    static BYTE manifest_bytes[4096];
    static BYTE actual_manifest[32],required_manifest[32],actual_binary[32];
    NoxManifest manifest;
    HANDLE f=INVALID_HANDLE_VALUE,download_file=INVALID_HANDLE_VALUE;
    DWORD p,n=0,version;unsigned long long downloaded=0;
    Hash hash;int r=0;
    unsigned int i;
    const char *pinned=NOX_PINNED_MANIFEST_SHA256_HEX;
    int nonzero=0;
    if(!nox_hex32(pinned,required_manifest)){
        say(L"LOADER_HOLD: trusted manifest pin missing or invalid.",MB_ICONERROR);return 1;
    }
    for(i=0;i<32;i++)nonzero|=required_manifest[i];
    if(!nonzero){say(L"LOADER_HOLD: no approved bootstrap release manifest is pinned.\nNothing will be downloaded or executed.",MB_ICONINFORMATION);return 1;}
    p=GetModuleFileNameW(0,manifest_path,MAX_PATH_W);
    if(p==0||p>=MAX_PATH_W-1)return 2;
    while(p && manifest_path[p-1]!=L'\\' && manifest_path[p-1]!=L'/')p--;
    manifest_path[p]=0;
    if(!wappend(manifest_path,MAX_PATH_W,CONFIG))return 2;
    f=CreateFileW(manifest_path,GENERIC_READ,FILE_SHARE_READ,0,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,0);
    if(f==INVALID_HANDLE_VALUE){say(L"LOADER_HOLD: no approved release manifest beside this EXE.",MB_ICONINFORMATION);return 3;}
    if(!ReadFile(f,manifest_bytes,sizeof(manifest_bytes),&n,0)||n<100||n>=sizeof(manifest_bytes)){
        CloseHandle(f);say(L"Invalid release manifest size.",MB_ICONERROR);return 4;
    }
    CloseHandle(f);f=INVALID_HANDLE_VALUE;
    if(!hash_buf(manifest_bytes,n,actual_manifest)||!digest_equal(actual_manifest,required_manifest,32)){
        say(L"MANIFEST_TAMPERED: manifest differs from this loader's owner-approved immutable SHA-256.\nNo network or execution performed.",MB_ICONERROR);return 5;
    }
    if(!nox_manifest_parse(manifest_bytes,n,&manifest)){
        say(L"MANIFEST_INVALID: wrong scheme, version, URL, size, or SHA-256.",MB_ICONERROR);return 6;
    }
    version=(DWORD)manifest.version;
    if(version<NOX_MIN_BOOTSTRAP_VERSION || !version_not_downgrade(version)){
        say(L"ROLLBACK_DENIED: this package is older than the previously approved Bootstrap version.",MB_ICONERROR);return 7;
    }
    if(MessageBoxW(0,L"Download the owner-pinned NOX HELION Bootstrap Setup over HTTPS, verify its exact SHA-256 and size, then start the Windows installer?\nNo hidden install or model download.",TITLE,MB_OKCANCEL|MB_ICONINFORMATION)!=IDOK)return 0;
    if(!GetTempPathW(MAX_PATH_W,temp_dir)||!GetTempFileNameW(temp_dir,L"NOX",0,temp_path))return 8;
    for(i=0;i<MAX_PATH_W;i++){exe_path[i]=temp_path[i];if(!temp_path[i])break;}
    if(!wappend(exe_path,MAX_PATH_W,L".exe")){DeleteFileW(temp_path);return 8;}
    download_file=CreateFileW(temp_path,GENERIC_WRITE,0,0,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,0);
    if(download_file==INVALID_HANDLE_VALUE){DeleteFileW(temp_path);return 8;}
    if(!hash_open(&hash)){
        hash_close(&hash);CloseHandle(download_file);DeleteFileW(temp_path);return 9;
    }
    r=https_download(manifest.url,download_file,manifest.size,&hash,&downloaded);
    if(r && downloaded==manifest.size)r=hash_finish(&hash,actual_binary)&&digest_equal(actual_binary,manifest.digest,32);
    hash_close(&hash);CloseHandle(download_file);download_file=INVALID_HANDLE_VALUE;
    if(!r){DeleteFileW(temp_path);say(L"DOWNLOAD_HOLD: HTTPS status/redirect, byte count or SHA-256 failed.\nDownloaded file deleted. Nothing executed.",MB_ICONERROR);return 10;}
    if(!has_mz(temp_path)){DeleteFileW(temp_path);say(L"Downloaded artifact is not a Windows PE file.",MB_ICONERROR);return 11;}
    if(!version_not_downgrade(version)){DeleteFileW(temp_path);return 12;}
    if(!MoveFileExW(temp_path,exe_path,MOVEFILE_WRITE_THROUGH)){
        DeleteFileW(temp_path);say(L"Verified installer could not be finalized safely.",MB_ICONERROR);return 13;
    }
    /* The registry witness blocks accidental downgraded installs for this user.
       Not a cryptographic defense against a hostile administrator/HKCU writer. */
    if(!remember_version(version)){DeleteFileW(exe_path);say(L"Cannot persist anti-rollback witness; install blocked.",MB_ICONERROR);return 14;}
    if((SIZE_T)ShellExecuteW(0,L"open",exe_path,0,0,1)<=32){
        say(L"Installer verified but Windows refused to start it.\nThe verified file remains in Temp.",MB_ICONERROR);return 15;
    }
    say(L"Owner-pinned installer verified and handed to Windows.\nFinish the installation wizard.\nThis is not proof of a completed NOX Release 1.",MB_ICONINFORMATION);
    return 0;
}
void *memset(void*p,int v,unsigned long long n){BYTE*b=(BYTE*)p;unsigned long long i;for(i=0;i<n;i++)b[i]=(BYTE)v;return p;}
void mainCRTStartup(void){ExitProcess((DWORD)run());}
