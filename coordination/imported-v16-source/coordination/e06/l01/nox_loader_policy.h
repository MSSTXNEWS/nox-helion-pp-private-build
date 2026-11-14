/* NOX HELION L01. Strict, dependency-free manifest policy.
   A manifest is trusted ONLY after its raw bytes match the loader's compiled SHA256.
   No URL, version or digest from this text is trustworthy without that check. */
#ifndef NOX_LOADER_POLICY_H
#define NOX_LOADER_POLICY_H

typedef struct {
    unsigned long version;
    unsigned long long size;
    char url[2048];
    unsigned char digest[32];
} NoxManifest;

static int nox_hex(int x) {
    if(x>='0'&&x<='9')return x-'0';
    if(x>='a'&&x<='f')return x-'a'+10;
    if(x>='A'&&x<='F')return x-'A'+10;
    return -1;
}
static unsigned long nox_strlen(const char *s, unsigned long max) {
    unsigned long n=0;
    while(n<max && s[n]) n++;
    return n;
}
static int nox_hex32(const char *s, unsigned char out[32]) {
    unsigned int i;
    if(nox_strlen(s,65)!=64)return 0;
    for(i=0;i<32;i++){
        int hi=nox_hex((unsigned char)s[i*2]);
        int lo=nox_hex((unsigned char)s[i*2+1]);
        if(hi<0||lo<0)return 0;
        out[i]=(unsigned char)(hi*16+lo);
    }
    return 1;
}
static int nox_same(const char *a,const char *b) {
    while(*a && *b) if(*a++!=*b++)return 0;
    return *a==*b;
}
static int nox_decimal(const char *s, unsigned long long ceiling, unsigned long long *num) {
    unsigned long long x=0;
    if(!*s || (*s=='0' && s[1]))return 0;
    for(;*s;s++){
        unsigned int d=(unsigned char)(*s)-(unsigned char)'0';
        if(d>9 || x>(ceiling-d)/10)return 0;
        x=x*10+d;
    }
    if(!x)return 0;
    *num=x;return 1;
}
static int nox_url(const char *s) {
    /* Full URL is bound to SHA-pinned manifest, but reject unsafe schemes,
       credentials, whitespace, controls, local IPs and noncanonical origins. */
    static const char pre[]="https://";
    const char *p=pre,*h,*end,*q;
    unsigned int hn=0;
    while(*p){if(*s++!=*p++)return 0;}
    h=s;
    while(*s && *s!='/' && *s!='?'){
        unsigned char c=(unsigned char)*s++;
        if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='.'||c=='-'))return 0;
        hn++;
        if(hn>253)return 0;
    }
    if(!hn || *h=='.' || *h=='-' || s[-1]=='.'||s[-1]=='-' || *s!='/')return 0;
    end=s;
    for(q=h;q<end;q++){
        if(*q=='.')break;
    }
    if(q==end)return 0; /* no single-label/local hosts */
    /* Do not accept dotted IPv4 or local names even in a signed manifest. */
    {
        const char *dot=end;
        int all_numeric=1;
        for(q=h;q<end;q++){
            if(!((*q>='0'&&*q<='9')||*q=='.'))all_numeric=0;
        }
        if(all_numeric)return 0;
        while(dot>h && dot[-1]!='.')dot--;
        if((end-dot)==5 && dot[0]=='l' && dot[1]=='o' && dot[2]=='c' && dot[3]=='a' && dot[4]=='l')return 0;
        if((end-dot)==8 && dot[0]=='i' && dot[1]=='n' && dot[2]=='t' && dot[3]=='e' && dot[4]=='r' && dot[5]=='n' && dot[6]=='a' && dot[7]=='l')return 0;
    }
    /* Unicode/hex IP addresses, embedded credentials and non-HTTPS are denied.
       No nonstandard port; no fragment or backslash; path must be nonempty. */
    if(!s[1])return 0;
    for(;*s;s++){
        unsigned char c=(unsigned char)*s;
        if(c<33||c>126||c=='#'||c=='\\'||c=='@')return 0;
    }
    return 1;
}
static int nox_manifest_parse(const unsigned char *in,unsigned long n,NoxManifest *out) {
    /* 5 canonical ASCII LF-delimited lines, final LF required.
       NOX-HELION-BOOTSTRAP-V2 \n VERSION \n HTTPS_URL \n SIZE \n SHA256 \n */
    static char lines[5][2048];
    unsigned int i=0,j=0,k=0;
    unsigned long long v=0, sz=0;
    if(n<100||n>4095||!out||in[n-1]!='\n')return 0;
    for(k=0;k<n;k++){
        unsigned char c=in[k];
        if(c=='\n'){
            if(i>=5)return 0;
            lines[i][j]=0;i++;j=0;
            if(i==5 && k!=n-1)return 0;
        }else{
            if(c<32||c>126 || i>=5 || j>=2047)return 0;
            lines[i][j++]=(char)c;
        }
    }
    if(i!=5 || !nox_same(lines[0],"NOX-HELION-BOOTSTRAP-V2"))return 0;
    if(!nox_decimal(lines[1],2147483647ULL,&v)||!nox_url(lines[2])||
       !nox_decimal(lines[3],2147483647ULL,&sz)|| sz<4096 ||
       !nox_hex32(lines[4],out->digest))return 0;
    for(k=0;k<2048;k++){
        out->url[k]=lines[2][k];
        if(!lines[2][k])break;
    }
    out->version=(unsigned long)v;
    out->size=sz;
    return 1;
}
#endif
