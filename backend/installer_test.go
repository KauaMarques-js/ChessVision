package main

import (
	"archive/zip"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestExtractEmbeddedApplication(t *testing.T) {
	dir := t.TempDir()
	if err := embedExtract(dir); err != nil {
		t.Fatal(err)
	}
	for _, f := range []string{"app.py", "tracker.py", "variation_view.py", "extension/manifest.json", "INSTALADOR_EXE.md"} {
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
