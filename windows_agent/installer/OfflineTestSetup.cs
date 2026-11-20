using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;

internal static class Program
{
    internal const string BuildId = "%%BUILD_ID%%";
    internal const string PayloadHash = "%%PAYLOAD_SHA256%%";
    internal const string Expiry = "%%EXPIRY%%";
    internal const string GraceEnd = "%%GRACE_END%%";

    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            if (!Environment.Is64BitOperatingSystem || Environment.OSVersion.Platform != PlatformID.Win32NT)
                throw new InvalidOperationException("This engineering package requires 64-bit Windows 10 or 11.");
#if LAUNCHER
            Launch(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location));
#else
            using (var instance = new Mutex(false, "Local\\VantagOfflineEngineeringSetup-" + BuildId))
            {
                if (!instance.WaitOne(0))
                    throw new InvalidOperationException("This test installer is already open. Use its existing window.");
                try { Application.Run(new SetupWindow()); }
                finally { instance.ReleaseMutex(); }
            }
#endif
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "Vantag Offline Test", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Environment.ExitCode = 1;
        }
    }

    internal static void Launch(string directory)
    {
        var executable = Path.Combine(directory, "engine", "VantagAgent.exe");
        if (!File.Exists(executable) || !File.Exists(Path.Combine(directory, "engine", "config.json")))
            throw new FileNotFoundException("The local application is incomplete. Run this test setup again; do not move the launcher out of its application folder.");
        var profile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Vantag", "OfflineEngineeringTest", "Sites", BuildId);
        Directory.CreateDirectory(profile);
        var start = new ProcessStartInfo(executable) {
            WorkingDirectory = Path.GetDirectoryName(executable), UseShellExecute = false, CreateNoWindow = true
        };
        start.EnvironmentVariables["USERPROFILE"] = profile;
        start.EnvironmentVariables["APPDATA"] = Path.Combine(profile, "AppData", "Roaming");
        start.EnvironmentVariables["LOCALAPPDATA"] = Path.Combine(profile, "AppData", "Local");
        Directory.CreateDirectory(start.EnvironmentVariables["APPDATA"]);
        Directory.CreateDirectory(start.EnvironmentVariables["LOCALAPPDATA"]);
        start.EnvironmentVariables.Remove("PYTHONHOME");
        start.EnvironmentVariables.Remove("PYTHONPATH");
        Process.Start(start);
    }
}

#if !LAUNCHER
internal sealed class SetupWindow : Form
{
    private readonly Label status = new Label();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly Button install = new Button();
    private readonly CheckBox openAfter = new CheckBox();
    private readonly BackgroundWorker worker = new BackgroundWorker();
    private readonly string destination;
    private bool installed;

    internal SetupWindow()
    {
        Text = "Vantag Offline Test Setup - 1.11.5";
        ClientSize = new Size(680, 480);
        MinimumSize = Size;
        MaximumSize = Size;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 10);
        Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
        destination = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Vantag", "OfflineEngineeringTest", "Apps", Program.BuildId);
        var heading = new Label { Text = "Offline Site Console | Engineering test", Location = new Point(24, 22), Size = new Size(630, 34), Font = new Font("Segoe UI", 16, FontStyle.Bold) };
        var explanation = new Label {
            Text = "Includes Python, application libraries, local console and AI models.\r\nNo separate Python, pip or internet download is required by setup.\r\nCPU operation is included; system GPU drivers are NOT changed.\r\n\r\n8-camera engineering entitlement: 3 days from package creation,\r\nthen the existing 7-day grace policy. NOT a production subscription.\r\nNo real-camera accuracy or clean-PC qualification is claimed.\r\nStaff matching, VLM, search, assistant and high-value counter unavailable.",
            Location = new Point(24, 68), Size = new Size(630, 180)
        };
        var dates = new Label { Text = "Active until: " + Program.Expiry + "\r\nGrace ends: " + Program.GraceEnd + " (UTC)", Location = new Point(24, 255), Size = new Size(630, 42) };
        var location = new TextBox { Text = destination, ReadOnly = true, Location = new Point(24, 305), Size = new Size(630, 25), TabStop = false };
        status.Text = "Installs only for this Windows user. Existing sites are not overwritten.";
        status.SetBounds(24, 340, 630, 40);
        progress.SetBounds(24, 385, 630, 20);
        openAfter.Text = "Open local owner setup after extraction";
        openAfter.Checked = true;
        openAfter.SetBounds(24, 422, 400, 25);
        install.Text = "Install and open";
        install.Name = "InstallButton";
        install.SetBounds(475, 417, 180, 36);
        install.Click += delegate {
            if (installed) { Close(); return; }
            install.Enabled = false;
            openAfter.Enabled = false;
            status.Text = "Verifying the embedded package. This may take a minute...";
            worker.RunWorkerAsync();
        };
        worker.WorkerReportsProgress = true;
        worker.DoWork += Extract;
        worker.ProgressChanged += delegate(object sender, ProgressChangedEventArgs args) { progress.Value = args.ProgressPercentage; status.Text = (string)args.UserState; };
        worker.RunWorkerCompleted += delegate(object sender, RunWorkerCompletedEventArgs args) {
            install.Enabled = true;
            openAfter.Enabled = true;
            if (args.Error != null) {
                status.Text = "Installation failed. Your existing site data was not deleted.";
                MessageBox.Show(args.Error.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            installed = true;
            progress.Value = 100;
            status.Text = "Installed. Use the Vantag Offline Test desktop shortcut to reopen it.";
            install.Text = "Close";
            if (openAfter.Checked) {
                try { Program.Launch(destination); }
                catch (Exception error) { MessageBox.Show(error.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error); }
            }
        };
        FormClosing += delegate(object sender, FormClosingEventArgs args) {
            if (worker.IsBusy) { args.Cancel = true; MessageBox.Show("Please wait for extraction to finish. It does not change existing site data.", Text); }
        };
        Controls.AddRange(new Control[] { heading, explanation, dates, location, status, progress, openAfter, install });
    }

    private void Extract(object sender, DoWorkEventArgs args)
    {
        var assembly = Assembly.GetExecutingAssembly();
        using (var payload = assembly.GetManifestResourceStream("vantag.payload.zip"))
        {
            if (payload == null) throw new InvalidDataException("The embedded application package is missing.");
            using (var algorithm = SHA256.Create()) {
                var actual = BitConverter.ToString(algorithm.ComputeHash(payload)).Replace("-", "").ToLowerInvariant();
                if (actual != Program.PayloadHash) throw new InvalidDataException("Package integrity check failed. Copy the setup EXE again from the supplied original.");
            }
            payload.Position = 0;
            using (var archive = new ZipArchive(payload, ZipArchiveMode.Read, true))
            {
                long required = archive.Entries.Sum(entry => entry.Length);
                var drive = new DriveInfo(Path.GetPathRoot(destination));
                if (drive.AvailableFreeSpace < required + 1024L * 1024 * 1024)
                    throw new IOException("Insufficient disk space. Keep at least 1 GB free in addition to the extracted application size.");
                var temporary = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Vantag", "Stage", Guid.NewGuid().ToString("N").Substring(0, 12));
                Directory.CreateDirectory(temporary);
                try
                {
                    long extracted = 0;
                    var root = Path.GetFullPath(temporary) + Path.DirectorySeparatorChar;
                    foreach (var entry in archive.Entries)
                    {
                        var target = Path.GetFullPath(Path.Combine(temporary, entry.FullName));
                        if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                            throw new InvalidDataException("Unsafe archive entry rejected.");
                        if (entry.FullName.EndsWith("/")) { Directory.CreateDirectory(target); continue; }
                        Directory.CreateDirectory(Path.GetDirectoryName(target));
                        using (var input = entry.Open())
                        using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
                            var buffer = new byte[1024 * 1024];
                            int count;
                            while ((count = input.Read(buffer, 0, buffer.Length)) > 0) {
                                output.Write(buffer, 0, count);
                                extracted += count;
                                worker.ReportProgress((int)Math.Min(98, extracted * 98 / Math.Max(1, required)), "Extracting application and models (" + (extracted / 1048576) + " MB)...");
                            }
                        }
                    }
                    foreach (var name in new[] { "VantagOfflineTest.exe", "engine/config.json", "engine/offline-entitlement.json", "engine/VantagAgent.exe", "engine/_internal/offline_keys.json" })
                        if (!File.Exists(Path.Combine(temporary, name))) throw new InvalidDataException("Required setup component missing: " + name);
                    if (Directory.Exists(destination))
                        throw new IOException("This test build is already installed. Open its Vantag Offline Test shortcut; no existing files were replaced.");
                    Directory.CreateDirectory(Path.GetDirectoryName(destination));
                    Directory.Move(temporary, destination);
                    CreateShortcut(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory));
                    CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Vantag Offline Test"));
                }
                finally { if (Directory.Exists(temporary)) Directory.Delete(temporary, true); }
            }
        }
    }

    private void CreateShortcut(string folder)
    {
        Directory.CreateDirectory(folder);
        var shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType == null) throw new InvalidOperationException("Windows shortcut support is unavailable. Open VantagOfflineTest.exe in " + destination);
        dynamic shell = Activator.CreateInstance(shellType);
        dynamic shortcut = shell.CreateShortcut(Path.Combine(folder, "Vantag Offline Test.lnk"));
        shortcut.TargetPath = Path.Combine(destination, "VantagOfflineTest.exe");
        shortcut.WorkingDirectory = destination;
        shortcut.Description = "Vantag Offline Site Console - isolated engineering test";
        shortcut.IconLocation = Path.Combine(destination, "VantagOfflineTest.exe") + ",0";
        shortcut.Save();
    }
}
#endif
