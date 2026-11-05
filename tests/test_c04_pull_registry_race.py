"""C04 source-stage regression for original P03 reviewed-pull queue boundary.

No new downloader, no weight install, and no claim of compiled .NET/native E07.
Run against the existing source tree: python -m unittest discover -s tests -p 'test_c04_pull_registry_race.py' -v
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Packages/P03/Source/P03.ModelCenter/ModelCenterNativeRoutes.cs"

class ReviewedPullRaceSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SOURCE.read_text(encoding="utf-8")
        cls.pull = source.split('case "models.pull":', 1)[1].split('default: throw', 1)[0]

    def test_native_consent_and_pinned_review_retained(self):
        self.assertIn('if (!nativeConsent)', self.pull)
        self.assertIn('artifacts.Length!=1', self.pull)
        self.assertIn('var model=artifacts[0];', self.pull)

    def test_revalidate_unique_tag_after_hardware_before_queue(self):
        self.assertIn('currentPullReview.Length!=1', self.pull)
        self.assertIn('currentPullReview[0]!=model', self.pull)
        self.assertIn('var currentPullReview=', self.pull)
        steps = ['RequireHardware(model);', 'var currentPullReview=',
                 'P03_PULL_REVIEW_CHANGED', '_queue.EnqueueVerifiedPullAsync(model,true,ct)']
        offsets = [self.pull.index(step) for step in steps]
        self.assertEqual(offsets, sorted(offsets))

    def test_native_stop_fenced_after_preflight(self):
        self.assertIn('var currentPullReview=', self.pull)
        a = self.pull.index('RequireHardware(model);')
        b = self.pull.index('var currentPullReview=')
        c = self.pull.index('_queue.EnqueueVerifiedPullAsync(model,true,ct)')
        self.assertIn('ct.ThrowIfCancellationRequested();', self.pull[a:b])
        self.assertIn('ct.ThrowIfCancellationRequested();', self.pull[b:c])

    def test_original_queue_and_transfer_only(self):
        self.assertIn('StartQueuedTransfer(job.Id)', self.pull)
        self.assertNotIn('Process.Start(', self.pull)
        self.assertNotIn('DownloadFile(', self.pull)
        self.assertNotIn('new ModelDownloadQueueStore(', self.pull)

if __name__ == '__main__':
    unittest.main()
