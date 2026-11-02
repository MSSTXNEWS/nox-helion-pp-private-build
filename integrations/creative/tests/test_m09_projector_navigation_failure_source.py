"""M09 source regression: failed asynchronous WebView2 theater navigation must retire only this projector."""
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "bridge" / "CreativeHostBridge.cs"

class ProjectorNavigationFailureSourceTest(unittest.TestCase):
    def test_async_failure_closes_only_current_projector(self):
        source = SOURCE.read_text(encoding="utf-8")
        method = source.split("private async Task OpenCreativeProjectorAsync", 1)[1].split(
            "private async Task<string> StopCreativeWorkerAsync", 1)[0]
        self.assertIn("CoreWebView2NavigationCompletedEventArgs", method)
        self.assertIn("projectorCore.NavigationCompleted -= projectorNavFinished;", method)
        self.assertIn("result.IsSuccess || !ReferenceEquals(_creativeProjector,theater)", method)
        self.assertIn('WriteLog("CREATIVE_PROJECTOR_NAVIGATION_HOLD "', method)
        subscribe = method.index("projectorCore.NavigationCompleted += projectorNavFinished;")
        navigate = method.index("projectorCore.Navigate(theaterUrl);")
        self.assertLess(subscribe, navigate)
        handler = method.split("projectorNavFinished = (_, result) =>", 1)[1].split(
            "projectorCore.NavigationCompleted += projectorNavFinished;", 1)[0]
        self.assertIn("try { theater.Close(); }", handler)
        self.assertIn("if (ReferenceEquals(_creativeProjector,theater))", handler)
        self.assertIn("_creativeProjector=null;", handler)
        self.assertIn("_creativeProjectorProjectId=null;", handler)
        self.assertIn("openingProjector.Close();", method)


    def test_project_media_mapping_checks_all_owner_data_ancestors(self):
        # SOURCE-ONLY: a junction at _data/creative is invisible to checks
        # limited to projects/, selected project/ and the media-file leaf.
        source = SOURCE.read_text(encoding="utf-8")
        helper = source.split("private static bool IsTrustedProjectorMediaTree(", 1)[1].split(
            "private async Task OpenCreativeProjectorAsync", 1)[0]
        method = source.split("private async Task OpenCreativeProjectorAsync", 1)[1].split(
            "private async Task<string> StopCreativeWorkerAsync", 1)[0]
        self.assertIn("Path.GetFullPath(dataRoot)", helper)
        self.assertIn("Path.GetFullPath(selectedFolder)", helper)
        self.assertIn("folder.StartsWith(root + Path.DirectorySeparatorChar", helper)
        self.assertIn("ancestor = ancestor.Parent", helper)
        self.assertIn("!ancestor.Exists || (ancestor.Attributes & FileAttributes.ReparsePoint) != 0", helper)
        self.assertIn("StringComparison.OrdinalIgnoreCase", helper)
        self.assertIn("IsTrustedProjectorMediaTree(_data,projectFolder)", method)
        self.assertLess(method.index("IsTrustedProjectorMediaTree(_data,projectFolder)"),
                        method.index("projectId = requestedProjectId;"))
        self.assertIn("FileInfo(movie).Attributes & FileAttributes.ReparsePoint", method)

    def test_retired_window_does_not_navigate_after_async_core_initialization(self):
        # An older EnsureCoreWebView2Async may resume after this window was
        # closed or superseded. The original owner must remain untouched.
        source = SOURCE.read_text(encoding="utf-8")
        method = source.split("private async Task OpenCreativeProjectorAsync", 1)[1].split(
            "private async Task<string> StopCreativeWorkerAsync", 1)[0]
        init = "await viewer.EnsureCoreWebView2Async(env);"
        guard = "if (!ReferenceEquals(_creativeProjector,theater) || !theater.IsVisible) return;"
        self.assertIn(guard, method)
        self.assertLess(method.index(init), method.index(guard))
        self.assertLess(method.index(guard),
                        method.index("viewer.CoreWebView2.Settings.AreHostObjectsAllowed=false;"))
        self.assertLess(method.index(guard), method.index("projectorCore.Navigate(theaterUrl);"))
        self.assertIn("if(ReferenceEquals(_creativeProjector,theater)){", method)

    def test_subtitle_owner_revalidates_projector_after_each_webview2_await(self):
        # Source-level regression: closed/replaced WebView2 must not receive a
        # later focus command or a false native READY acknowledgement.
        source = SOURCE.read_text(encoding="utf-8")
        route = source.split("private async Task<string> OpenOwnerMediaRouteAsync", 1)[1].split(
            "private static bool IsTrustedProjectorMediaTree", 1)[0]
        guard = ('if (!ReferenceEquals(_creativeProjector, projector) ||\\n'
                 '                !projector.IsVisible ||\\n'
                 '                !ReferenceEquals(FindNoxTheaterViewer(projector), viewer))\\n'
                 '                return "MEDIA_OWNER_UI_NOT_READY";')
        self.assertEqual(route.count(guard), 2)
        probe = route.index('var found = await viewer.CoreWebView2.ExecuteScriptAsync(')
        focus = route.index("document.getElementById('subtitles').focus();")
        ready = route.index('return "SUBTITLE_PICKER_READY_NOT_IMPORTED";')
        first = route.index(guard, probe)
        second = route.index(guard, focus)
        self.assertLess(probe, first)
        self.assertLess(first, focus)
        self.assertLess(focus, second)
        self.assertLess(second, ready)
        self.assertIn("stop.ThrowIfCancellationRequested();", route[probe:first])
        self.assertIn("stop.ThrowIfCancellationRequested();", route[focus:second])


if __name__ == "__main__":
    unittest.main()
