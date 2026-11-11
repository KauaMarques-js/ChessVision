package main

import (
	"archive/zip"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestExtractEmbeddedApplication(t *testing.T) {
	dir := t.TempDir()
	if err := embedExtract(dir); err != nil {
		t.Fatal(err)
	}
	for _, f := range []string{"app.py", "tracker.py", "variation_view.py", "screen_reader.py", "extension/manifest.json", "INSTALADOR_EXE.md"} {
		if info, err := os.Stat(filepath.Join(dir, filepath.FromSlash(f))); err != nil || info.Size() == 0 {
			t.Fatalf("arquivo ausente %s: %v", f, err)
		}
	}
	if err := embedExtract(dir); err != nil {
		t.Fatalf("extracao idempotente: %v", err)
	}
}

func TestZipSlipRejected(t *testing.T) {
	root := t.TempDir()
	archive := filepath.Join(root, "bad.zip")
	f, err := os.Create(archive)
	if err != nil {
		t.Fatal(err)
	}
	z := zip.NewWriter(f)
	w, err := z.Create("../escape.txt")
	if err != nil {
		t.Fatal(err)
	}
	_, _ = w.Write([]byte("bad"))
	_ = z.Close()
	_ = f.Close()
	err = unpackZip(archive, filepath.Join(root, "data"))
	if err == nil || !strings.Contains(err.Error(), "inseguro") {
		t.Fatalf("zip-slip nao bloqueado: %v", err)
	}
}

func TestTkProbesCreateAWindow(t *testing.T) {
	for _, probe := range []string{tkinterProbe, venvProbe} {
		if !strings.Contains(probe, "tk.Tk()") || !strings.Contains(probe, "root.destroy()") {
			t.Errorf("probe does not create and destroy a Tk window: %s", probe)
		}
	}
}

func TestCleanPythonEnv(t *testing.T) {
	before := []string{"PATH=C:\\Windows", "TCL_LIBRARY=C:\\bad", "TK_LIBRARY=C:\\wrong", "PYTHONHOME=x", "PYTHONPATH=y", "HOME=x"}
	after := cleanPythonEnv(before)
	if len(after) != 2 || after[0] != before[0] || after[1] != before[5] {
		t.Fatalf("environment was not sanitized: %#v", after)
	}
}

func TestLaunchUpdatesMissingDependenciesWithoutRecreatingVenv(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows venv layout")
	}
	python, err := exec.LookPath("python")
	if err != nil || !pythonValid(python) {
		t.Skip("Python with working Tk unavailable")
	}
	// Exercise real subprocesses and Tk with an offline pip stub. Never download
	// packages or modify the user's interpreter during a regression test.
	t.Setenv("PIP_NO_INDEX", "1")
	dest := t.TempDir()
	venv := filepath.Join(dest, ".venv")
	if err := runCommand(time.Minute, dest, python, "-m", "venv", "--without-pip", venv); err != nil {
		t.Fatal(err)
	}
	exe := filepath.Join(venv, "Scripts", "python.exe")
	packages := filepath.Join(venv, "Lib", "site-packages")
	files := map[string]string{
		filepath.Join(packages, "chess", "__init__.py"): "Board = object\n",
		filepath.Join(packages, "chess", "engine.py"):   "",
		filepath.Join(packages, "pip", "__init__.py"):   "",
		filepath.Join(packages, "pip", "__main__.py"): `import sys
from pathlib import Path
with (Path(sys.prefix).parent / 'pip-calls.txt').open('a') as log:
    log.write(' '.join(sys.argv[1:]) + '\n')
target = Path(__file__).resolve().parents[1] / 'PIL'
target.mkdir(exist_ok=True)
for name in ('__init__.py', 'ImageGrab.py', 'ImageTk.py'):
    (target / name).write_text('')
`,
		filepath.Join(venv, "keep.txt"):         "preserve this environment",
		filepath.Join(dest, "config.json"):      "{\"depth\":42}",
		filepath.Join(dest, "requirements.txt"): "Pillow==13.0.0\n",
	}
	for path, data := range files {
		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(data), 0644); err != nil {
			t.Fatal(err)
		}
	}
	if err := checkVenv(exe); err == nil || !strings.Contains(err.Error(), "PIL") {
		t.Fatalf("expected a diagnostic for missing Pillow, got %v", err)
	}
	for attempt := 0; attempt < 2; attempt++ {
		prepared, err := ensureLaunchVenv(dest)
		if err != nil || prepared != exe {
			t.Fatalf("prepare launch: %s %v", prepared, err)
		}
	}
	for _, path := range []string{filepath.Join(venv, "keep.txt"), filepath.Join(dest, "config.json")} {
		if data, err := os.ReadFile(path); err != nil || string(data) != files[path] {
			t.Fatalf("existing data changed: %s %v", path, err)
		}
	}
	calls, err := os.ReadFile(filepath.Join(dest, "pip-calls.txt"))
	if err != nil || strings.Count(string(calls), "\n") != 1 || !strings.Contains(string(calls), "-r "+filepath.Join(dest, "requirements.txt")) {
		t.Fatalf("expected exactly one dependency update: %s %v", calls, err)
	}
}
