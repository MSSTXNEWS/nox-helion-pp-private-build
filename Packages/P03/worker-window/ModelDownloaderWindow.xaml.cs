using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace NoxHelion.P03.WorkerWindow;

/// <summary>
/// Immutable, owner-supplied evidence for one downloadable artifact.
/// The UI deliberately fails closed when any provenance field is unknown.
/// </summary>
public sealed record ModelArtifactEvidence(
    string CatalogId,
    string ArtifactName,
    string LicenseId,
    string LicenseEvidenceUrl,
    string ResolvedRevision,
    long SizeBytes,
    string Sha256,
    decimal? RequiredVramGiB,
    string CompatibilityEvidenceUrl,
    string SourceCommit,
    string SourceTree,
    string SourceLockTree,
    string OwnerReceiptId,
    string OwnerReceiptSourceCommit,
    string OwnerReceiptSourceTree,
    string OwnerReceiptPath,
    string OwnerReceiptPreimageSha256,
    string OwnerReceiptPostimageSha256,
    string OwnerReceiptPatchSha256);

/// <summary>
/// Code-only WPF window. Download/import execution stays with the existing host
/// adapter through events; this view does not introduce another downloader.
/// </summary>
public sealed class ModelDownloaderWindow : Window
{
    private readonly ListBox _catalog = new();
    private readonly TextBlock _details = new();
    private readonly TextBlock _status = new();
    private readonly TextBox _availableVram = new() { Text = string.Empty, Width = 110 };
    private readonly Button _download = new() { Content = "Скачать", IsEnabled = false, MinWidth = 120 };
    private readonly Button _import = new() { Content = "Импортировать", IsEnabled = false, MinWidth = 140 };
    private readonly IReadOnlyList<ModelArtifactEvidence> _artifacts;

    public event Action<ModelArtifactEvidence>? DownloadRequested;
    public event Action<ModelArtifactEvidence>? ImportRequested;

    public ModelDownloaderWindow(IEnumerable<ModelArtifactEvidence> artifacts)
    {
        _artifacts = (artifacts ?? Array.Empty<ModelArtifactEvidence>()).ToArray();
        Title = "NOX HELION · Каталог моделей";
        Width = 960;
        Height = 650;
        MinWidth = 720;
        MinHeight = 480;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Background = new SolidColorBrush(Color.FromRgb(15, 18, 24));
        Foreground = Brushes.White;

        _catalog.ItemsSource = _artifacts;
        _catalog.DisplayMemberPath = nameof(ModelArtifactEvidence.ArtifactName);
        _catalog.SelectionChanged += (_, _) => RefreshEvidence();

        var root = new Grid { Margin = new Thickness(20) };
        root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(2, GridUnitType.Star) });
        root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(3, GridUnitType.Star) });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        var title = new TextBlock
        {
            Text = "Модели и артефакты",
            FontSize = 24,
            FontWeight = FontWeights.SemiBold,
            Margin = new Thickness(0, 0, 0, 16)
        };
        Grid.SetColumnSpan(title, 2);
        root.Children.Add(title);

        var listBorder = new Border
        {
            BorderBrush = new SolidColorBrush(Color.FromRgb(58, 66, 82)),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(8),
            Padding = new Thickness(8),
            Margin = new Thickness(0, 0, 14, 0),
            Child = _catalog
        };
        Grid.SetRow(listBorder, 1);
        root.Children.Add(listBorder);

        var right = new StackPanel();
        right.Children.Add(new TextBlock
        {
            Text = "Подтверждённые сведения",
            FontSize = 16,
            FontWeight = FontWeights.SemiBold,
            Margin = new Thickness(0, 0, 0, 10)
        });
        _details.TextWrapping = TextWrapping.Wrap;
        _details.Margin = new Thickness(0, 0, 0, 12);
        right.Children.Add(_details);

        var vramRow = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 12) };
        vramRow.Children.Add(new TextBlock
        {
            Text = "Доступно VRAM, GiB (введите вручную):",
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(0, 0, 10, 0)
        });
        _availableVram.TextChanged += (_, _) => RefreshEvidence();
        vramRow.Children.Add(_availableVram);
        right.Children.Add(vramRow);

        _status.TextWrapping = TextWrapping.Wrap;
        _status.Margin = new Thickness(0, 0, 0, 12);
        right.Children.Add(_status);
        Grid.SetColumn(right, 1);
        Grid.SetRow(right, 1);
        root.Children.Add(right);

        var actions = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right
        };
        _download.Margin = new Thickness(0, 0, 10, 0);
        _download.Click += (_, _) =>
        {
            if (SelectedEligible() is { } artifact)
                DownloadRequested?.Invoke(artifact);
        };
        _import.Click += (_, _) =>
        {
            if (SelectedEligible() is { } artifact)
                ImportRequested?.Invoke(artifact);
        };
        actions.Children.Add(_download);
        actions.Children.Add(_import);
        Grid.SetRow(actions, 2);
        Grid.SetColumnSpan(actions, 2);
        root.Children.Add(actions);

        Content = root;
        if (_artifacts.Count > 0)
            _catalog.SelectedIndex = 0;
        else
            SetBlocked("Каталог пуст. До получения подтверждённых данных загрузка и импорт закрыты.");
    }

    private ModelArtifactEvidence? SelectedEligible()
    {
        if (_catalog.SelectedItem is not ModelArtifactEvidence artifact || !IsEligible(artifact, out _))
            return null;
        return artifact;
    }

    private bool IsEligible(ModelArtifactEvidence artifact, out string reason)
    {
        if (string.IsNullOrWhiteSpace(artifact.CatalogId) ||
            string.IsNullOrWhiteSpace(artifact.ArtifactName))
            return Block("Нет идентификатора выбранного артефакта.", out reason);
        if (string.IsNullOrWhiteSpace(artifact.LicenseId) ||
            !IsHttpsEvidence(artifact.LicenseEvidenceUrl))
            return Block("Лицензия или её источник не подтверждены.", out reason);
        if (!Regex.IsMatch(artifact.ResolvedRevision ?? string.Empty, "^[0-9a-fA-F]{40}$"))
            return Block("Не закреплена неизменяемая ревизия commit SHA.", out reason);
        if (artifact.SizeBytes <= 0)
            return Block("Размер артефакта неизвестен.", out reason);
        if (!Regex.IsMatch(artifact.Sha256 ?? string.Empty, "^[0-9a-fA-F]{64}$"))
            return Block("SHA-256 артефакта неизвестен или некорректен.", out reason);
        if (artifact.RequiredVramGiB is null || artifact.RequiredVramGiB <= 0 ||
            !IsHttpsEvidence(artifact.CompatibilityEvidenceUrl))
            return Block("Совместимость/требование VRAM не подтверждены источником.", out reason);
        if (!decimal.TryParse(_availableVram.Text, NumberStyles.Number, CultureInfo.InvariantCulture, out var available) ||
            available <= 0 || available < artifact.RequiredVramGiB.Value)
            return Block("Доступная VRAM не указана или меньше подтверждённого требования.", out reason);
        if (!IsGitObjectId(artifact.SourceCommit) ||
            !IsGitObjectId(artifact.SourceTree) ||
            !IsGitObjectId(artifact.SourceLockTree) ||
            !string.Equals(artifact.SourceTree, artifact.SourceLockTree, StringComparison.OrdinalIgnoreCase))
            return Block("Исходное дерево не совпадает с активным SourceLock.", out reason);
        if (string.IsNullOrWhiteSpace(artifact.OwnerReceiptId) ||
            !IsGitObjectId(artifact.OwnerReceiptSourceCommit) ||
            !IsGitObjectId(artifact.OwnerReceiptSourceTree) ||
            !string.Equals(artifact.OwnerReceiptSourceCommit, artifact.SourceCommit, StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(artifact.OwnerReceiptSourceTree, artifact.SourceTree, StringComparison.OrdinalIgnoreCase) ||
            string.IsNullOrWhiteSpace(artifact.OwnerReceiptPath) ||
            !IsSha256(artifact.OwnerReceiptPreimageSha256) ||
            !IsSha256(artifact.OwnerReceiptPostimageSha256) ||
            !IsSha256(artifact.OwnerReceiptPatchSha256))
            return Block("Owner receipt не привязан к точному пути, commit/tree и pre/postimage/patch SHA.", out reason);

        reason = "Поля provenance и совместимости подтверждены.";
        return true;
    }

    private static bool IsHttpsEvidence(string? value) =>
        Uri.TryCreate(value, UriKind.Absolute, out var uri) &&
        string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase);

    private static bool IsGitObjectId(string? value) =>
        Regex.IsMatch(value ?? string.Empty, "^[0-9a-fA-F]{40}$");

    private static bool IsSha256(string? value) =>
        Regex.IsMatch(value ?? string.Empty, "^[0-9a-fA-F]{64}$");

    private static bool Block(string message, out string reason)
    {
        reason = message;
        return false;
    }

    private void RefreshEvidence()
    {
        if (_catalog.SelectedItem is not ModelArtifactEvidence artifact)
        {
            SetBlocked("Выберите артефакт.");
            return;
        }

        var eligible = IsEligible(artifact, out var reason);
        _details.Text =
            $"Каталог: {artifact.CatalogId}\n" +
            $"Артефакт: {artifact.ArtifactName}\n" +
            $"Лицензия: {ValueOrUnknown(artifact.LicenseId)}\n" +
            $"Ревизия: {ValueOrUnknown(artifact.ResolvedRevision)}\n" +
            $"Размер: {(artifact.SizeBytes > 0 ? artifact.SizeBytes.ToString(CultureInfo.InvariantCulture) + " bytes" : "неизвестен")}\n" +
            $"SHA-256: {ValueOrUnknown(artifact.Sha256)}\n" +
            $"Минимальная VRAM: {(artifact.RequiredVramGiB.HasValue ? artifact.RequiredVramGiB.Value.ToString(CultureInfo.InvariantCulture) + " GiB" : "неизвестна")}\n" +
            $"Source: {ValueOrUnknown(artifact.SourceCommit)} / {ValueOrUnknown(artifact.SourceTree)}\n" +
            $"SourceLock tree: {ValueOrUnknown(artifact.SourceLockTree)}\n" +
            $"Owner receipt: {ValueOrUnknown(artifact.OwnerReceiptId)}\n" +
            $"Receipt source: {ValueOrUnknown(artifact.OwnerReceiptSourceCommit)} / {ValueOrUnknown(artifact.OwnerReceiptSourceTree)}\n" +
            $"Receipt path: {ValueOrUnknown(artifact.OwnerReceiptPath)}\n" +
            $"Receipt SHA-256 pre/post/patch: {ValueOrUnknown(artifact.OwnerReceiptPreimageSha256)} / {ValueOrUnknown(artifact.OwnerReceiptPostimageSha256)} / {ValueOrUnknown(artifact.OwnerReceiptPatchSha256)}";

        _status.Text = eligible ? reason : "BLOCKED · " + reason;
        _status.Foreground = eligible ? Brushes.LightGreen : Brushes.Orange;
        _download.IsEnabled = eligible;
        _import.IsEnabled = eligible;
    }

    private void SetBlocked(string message)
    {
        _details.Text = string.Empty;
        _status.Text = "BLOCKED · " + message;
        _status.Foreground = Brushes.Orange;
        _download.IsEnabled = false;
        _import.IsEnabled = false;
    }

    private static string ValueOrUnknown(string? value) =>
        string.IsNullOrWhiteSpace(value) ? "неизвестно" : value;
}
