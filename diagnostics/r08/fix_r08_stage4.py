#!/usr/bin/env python3
"""Compile-only repair of historical WPF sources, in a verified disposable build tree."""
import hashlib,sys,json
from pathlib import Path
assert len(sys.argv)==2
root=Path(sys.argv[1]).resolve()
expected={
 'Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs':'c2c7470d51ba3fc238517fd138666eee73a3d7c8a68cc8532d1585bd57c88166',
 'Packages/P03/worker-queue/ModelDownloadQueueStore.cs':'0d16e6e9673a7c069e91cadb674a1aea9123901756748f10609a4429fdf4efa0',
 'Contracts/EventV3Bridge.cs':'b4dc4b2352cc5e2f74b0eddc12db58147aea97316658b911aab8689675cfb8ca',
}
def sha(b):return hashlib.sha256(b).hexdigest()
for path,v in expected.items():
 p=root/path;b=p.read_bytes();a=sha(b)
 if a!=v:raise SystemExit('HOLD_R08_STAGE4_SOURCE_MISMATCH '+path+' '+a)
 s=b.decode('utf-8')
 if path.endswith('ModelDownloaderWindow.xaml.cs'):
  pairs=[
   ('_queueStore.Items.CollectionChanged += _queueItemsChanged;', '((System.Collections.Specialized.INotifyCollectionChanged)_queueStore.Items).CollectionChanged += _queueItemsChanged;'),
   ('_queueStore.Items.CollectionChanged -= _queueItemsChanged;', '((System.Collections.Specialized.INotifyCollectionChanged)_queueStore.Items).CollectionChanged -= _queueItemsChanged;'),
   ('var hasCompleted = item.HasBytesCompletedMeasurement;', 'var hasCompleted = item.BytesCompleted > 0;'),
   ('var hasTotal = item.HasBytesTotalMeasurement;', 'var hasTotal = item.BytesTotal > 0;'),
   ('var percent = bytesTotal is > 0 && bytesCompleted is not null', 'double? percent = bytesTotal is > 0 && bytesCompleted is not null')
  ]
 elif path.endswith('ModelDownloadQueueStore.cs'):
  pairs=[('new List<PersistedItem>(records.Count)', 'new List<PersistedQueueItem>(records.Count)')]
 else:
  pairs=[('var completed = total.HasValue && sourceEvent.BytesCompleted is >= 0', 'long? completed = total.HasValue && sourceEvent.BytesCompleted is >= 0')]
 for a,b in pairs:
  if s.count(a)!=1:raise SystemExit('HOLD_STAGE4_EXPECTED_EXACT_ONCE '+path+' '+a)
  s=s.replace(a,b,1)
 post=s.encode('utf-8');p.write_bytes(post)
 print('R08_STAGE4_SCOPED',path,'pre',v,'post',sha(post))
import_path=root/'NoLossDiagnosticsGlobalUsings.cs'
if import_path.exists():raise SystemExit('HOLD_R08_GLOBAL_IMPORT_COLLISION')
import_path.write_text('global using System.IO;\n',encoding='utf-8')
print('R08_STAGE4_GLOBAL_SYSTEM_IO_ADDED_IN_TEMP_ONLY',sha(import_path.read_bytes()))