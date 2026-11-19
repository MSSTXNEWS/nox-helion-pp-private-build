#!/usr/bin/env python3
"""Only two known oversized future-NOX source trees, pinned Git rev and real CRC.
Independent from the already verified 12/14 archives: no duplicate downloads.
"""
import download_v29_extra_sources as acquisition
acquisition.REPOS["flashinfer"]=["flashinfer-ai/flashinfer"]
acquisition.REPOS["tau2"]=["sierra-research/tau2-bench"]
acquisition.LIMIT_PER_REPO=400_000_000
if __name__=="__main__":
    acquisition.main()
