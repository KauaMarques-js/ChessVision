// ChessVision Lab 2.1 installer/launcher for Windows (amd64).
// Build: GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o ChessVisionLab-Instalador.exe installer.go
package main

import (
	"archive/zip"
	"bytes"
	"context"
	"embed"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

//go:embed payload
var payload embed.FS

const (
	pythonVersion = "3.14.10"
	pythonURL     = "https://www.python.org/ftp/python/3.14.10/python-3.14.10-amd64.exe"
	stockfishURL  = "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip"
)

var logger io.Writer = os.Stdout

// Third-party environment overrides can point Tk to another Python installation.
// Keep the app's interpreter self-contained, without changing the user's settings.
func cleanPythonEnv(env []string) []string {
	blocked := map[string]bool{
		"TCL_LIBRARY": true, "TK_LIBRARY": true,
		"PYTHONHOME": true, "PYTHONPATH": true,
	}
	clean := make([]string, 0, len(env))
	for _, pair := range env {
		name, _, ok := strings.Cut(pair, "=")
		if ok && blocked[strings.ToUpper(name)] {
			continue
		}
		clean = append(clean, pair)
	}
	return clean
}

// Importing tkinter is not enough: it succeeds even if init.tcl is missing.
const tkinterProbe = "import sys,tkinter as tk,venv,ensurepip; assert sys.version_info >= (3,11); root=tk.Tk();root.withdraw();root.update_idletasks();root.destroy()"
const venvProbe = "import chess,chess.engine,tkinter as tk; assert hasattr(chess, 'Board'); root=tk.Tk();root.withdraw();root.update_idletasks();root.destroy()"

func say(format string, args ...any) {
	s := fmt.Sprintf(format, args...)
	fmt.Fprintln(logger, s)
}

func stage(n int, name string) {
	say("\n========================================================")
	say(" ETAPA %d/7 - %s", n, name)
	say("========================================================")
}

func installPath() (string, error) {
	if runtime.GOOS != "windows" { // for development self-test on Linux
		if p := os.Getenv("CHESSVISION_TEST_HOME"); p != "" {
			return p, nil
		}
		return "", errors.New("o instalador e exclusivo para Windows")
	}
	local := os.Getenv("LOCALAPPDATA")
	if local == "" {
		return "", errors.New("LOCALAPPDATA nao encontrado")
	}
	return filepath.Join(local, "ChessVisionLab"), nil
}

func embedExtract(dest string) error {
	return fs.WalkDir(payload, "payload/ChessVisionLab", func(name string, ent fs.DirEntry, readErr error) error {
		if readErr != nil {
			return readErr
		}
		rel := strings.TrimPrefix(strings.TrimPrefix(name, "payload/ChessVisionLab"), "/")
		if rel == "" {
			return nil
		}
		destPath := filepath.Join(dest, filepath.FromSlash(rel))
		if ent.IsDir() {
			return os.MkdirAll(destPath, 0755)
		}
		data, err := payload.ReadFile(name)
		if err != nil {
			return err
		}
		if existing, err := os.ReadFile(destPath); err == nil && bytes.Equal(existing, data) {
			return nil
		}
		if err := os.MkdirAll(filepath.Dir(destPath), 0755); err != nil {
			return err
		}
		tmp := destPath + ".tmp"
		if err := os.WriteFile(tmp, data, 0644); err != nil {
			return err
		}
		if err := os.Rename(tmp, destPath); err != nil {
			os.Remove(tmp)
			return err
		}
		return nil
	})
}

func runCommand(timeout time.Duration, dir string, binary string, args ...string) error {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, binary, args...)
	hideWindow(cmd)
	cmd.Dir = dir
	cmd.Stdout = logger
	cmd.Stderr = logger
	cmd.Env = cleanPythonEnv(os.Environ())
	if err := cmd.Run(); err != nil {
		if ctx.Err() != nil {
			return fmt.Errorf("tempo esgotado: %s", binary)
		}
		return fmt.Errorf("comando %s falhou: %w", binary, err)
	}
	return nil
}

func pythonValid(executable string) bool {
	if _, err := os.Stat(executable); err != nil {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, executable, "-c", tkinterProbe)
	hideWindow(cmd)
	cmd.Env = cleanPythonEnv(os.Environ())
	return cmd.Run() == nil
}

func pythonFromLauncher() string {
	// py -3 reports sys.executable, allowing paths containing spaces.
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "py", "-3", "-c", "import sys;print(sys.executable)")
	hideWindow(cmd)
	cmd.Env = cleanPythonEnv(os.Environ())
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	parts := strings.Split(strings.TrimSpace(string(out)), "\n")
	value := strings.TrimSpace(parts[len(parts)-1])
	if pythonValid(value) {
		return value
	}
	return ""
}

func findPython(dest string) string {
	candidates := []string{filepath.Join(dest, "runtime", "python", "python.exe")}
	if p := pythonFromLauncher(); p != "" {
		candidates = append(candidates, p)
	}
	if p, err := exec.LookPath("python"); err == nil {
		candidates = append(candidates, p)
	}
	if p, err := exec.LookPath("python3"); err == nil {
		candidates = append(candidates, p)
	}
	for _, p := range candidates {
		if pythonValid(p) {
			return p
		}
	}
	return ""
}

func download(url, to string) error {
	if stat, err := os.Stat(to); err == nil && stat.Size() > 100000 {
		say("Arquivo armazenado: %s", to)
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(to), 0755); err != nil {
		return err
	}
	tmp := to + ".partial"
	os.Remove(tmp)
	file, err := os.Create(tmp)
	if err != nil {
		return err
	}
	defer file.Close()
	client := &http.Client{Timeout: 18 * time.Minute}
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", "ChessVisionLab-Installer/2.0")
	response, err := client.Do(req)
	if err != nil {
		os.Remove(tmp)
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		os.Remove(tmp)
		return fmt.Errorf("download retornou HTTP %d (%s)", response.StatusCode, url)
	}
	expected := response.ContentLength
	buf := make([]byte, 256*1024)
	var total int64
	last := time.Now()
	for {
		n, e := response.Body.Read(buf)
		if n > 0 {
			wn, we := file.Write(buf[:n])
			if we != nil {
				os.Remove(tmp)
				return we
			}
			if wn != n {
				return io.ErrShortWrite
			}
			total += int64(n)
			if time.Since(last) > 5*time.Second {
				if expected > 0 {
					say("Baixados %.1f de %.1f MB (%.0f%%)", float64(total)/1048576, float64(expected)/1048576, float64(total)*100/float64(expected))
				} else {
					say("Baixados %.1f MB", float64(total)/1048576)
				}
				last = time.Now()
			}
		}
		if e == io.EOF {
			break
		}
		if e != nil {
			os.Remove(tmp)
			return e
		}
	}
	if expected > 0 && total != expected {
		os.Remove(tmp)
		return fmt.Errorf("download incompleto: %d/%d bytes", total, expected)
	}
	if total < 100000 {
		os.Remove(tmp)
		return errors.New("arquivo baixado e muito pequeno")
	}
	if err := file.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, to)
}

func ensurePython(dest string) (string, error) {
	if p := findPython(dest); p != "" {
		say("Python detectado: %s", p)
		return p, nil
	}
	say("Nao encontrei um Python capaz de abrir janelas Tk (init.tcl).")
	say("Preparando Python %s isolado, sem alterar seu Python global...", pythonVersion)
	installer := filepath.Join(dest, "downloads", "python-"+pythonVersion+"-amd64.exe")
	if err := download(pythonURL, installer); err != nil {
		return "", fmt.Errorf("falha ao baixar Python oficial: %w", err)
	}
	target := filepath.Join(dest, "runtime", "python")
	err := runCommand(10*time.Minute, dest, installer, "/quiet", "InstallAllUsers=0", "TargetDir="+target, "PrependPath=0", "Include_launcher=0", "Include_pip=1", "Include_tcltk=1", "Include_test=0", "Shortcuts=0", "AssociateFiles=0")
	if err != nil {
		return "", err
	}
	p := filepath.Join(target, "python.exe")
	if !pythonValid(p) {
		return "", errors.New("Python privado foi instalado, mas ainda nao conseguiu abrir Tk (init.tcl). Consulte instalacao.log")
	}
	say("Python instalado e validado: %s", p)
	return p, nil
}

func venvValid(p string) bool {
	if _, err := os.Stat(p); err != nil {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, p, "-c", venvProbe)
	hideWindow(cmd)
	cmd.Env = cleanPythonEnv(os.Environ())
	return cmd.Run() == nil
}

func ensureVenv(dest, python string, repair bool) (string, error) {
	venv := filepath.Join(dest, ".venv")
	exe := filepath.Join(venv, "Scripts", "python.exe")
	if !repair && venvValid(exe) {
		say("Dependencias Python E janela Tk aprovadas. Sem reinstalacao.")
		return exe, nil
	}
	if _, err := os.Stat(venv); err == nil {
		say("Recriando ambiente Python para corrigir dependencias...")
		if err := os.RemoveAll(venv); err != nil {
			return "", err
		}
	}
	if err := runCommand(3*time.Minute, dest, python, "-m", "venv", venv); err != nil {
		return "", err
	}
	if err := runCommand(8*time.Minute, dest, exe, "-m", "pip", "install", "--disable-pip-version-check", "-r", filepath.Join(dest, "requirements.txt")); err != nil {
		return "", err
	}
	if !venvValid(exe) {
		return "", errors.New("ambiente virtual nao conseguiu abrir janela Tk ou carregar python-chess")
	}
	return exe, nil
}

func findStockfish(dest string) string {
	root := filepath.Join(dest, "engine")
	found := ""
	_ = filepath.WalkDir(root, func(p string, d fs.DirEntry, err error) error {
		if err != nil || d == nil {
			return nil
		}
		if !d.IsDir() && strings.HasPrefix(strings.ToLower(d.Name()), "stockfish") && strings.HasSuffix(strings.ToLower(d.Name()), ".exe") {
			found = p
			return filepath.SkipAll
		}
		return nil
	})
	return found
}

func isStockfish19(bin string) bool {
	if bin == "" {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, bin)
	hideWindow(cmd)
	cmd.Stdin = strings.NewReader("uci\nquit\n")
	out, err := cmd.CombinedOutput()
	return err == nil && bytes.Contains(out, []byte("Stockfish 19")) && bytes.Contains(out, []byte("uciok"))
}

func unpackZip(source, target string) error {
	r, err := zip.OpenReader(source)
	if err != nil {
		return err
	}
	defer r.Close()
	if err := os.MkdirAll(target, 0755); err != nil {
		return err
	}
	var sum uint64
	for _, f := range r.File {
		clean := path.Clean(f.Name)
		if clean == "." || path.IsAbs(clean) || clean == ".." || strings.HasPrefix(clean, "../") || strings.Contains(clean, ":") {
			return fmt.Errorf("caminho inseguro no ZIP: %q", f.Name)
		}
		if f.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("link simbolico nao permitido: %s", clean)
		}
		if f.UncompressedSize64 > 500*1024*1024 {
			return fmt.Errorf("arquivo grande demais: %s", clean)
		}
		sum += f.UncompressedSize64
		if sum > 800*1024*1024 {
			return errors.New("ZIP excede limite de extracao")
		}
		out := filepath.Join(target, filepath.FromSlash(clean))
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(out, 0755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(out), 0755); err != nil {
			return err
		}
		rc, err := f.Open()
		if err != nil {
			return err
		}
		fp, err := os.Create(out + ".partial")
		if err != nil {
			rc.Close()
			return err
		}
		n, err := io.Copy(fp, io.LimitReader(rc, int64(f.UncompressedSize64)+1))
		fp.Close()
		rc.Close()
		if err != nil {
			return err
		}
		if uint64(n) != f.UncompressedSize64 {
			return fmt.Errorf("tamanho invalido ao extrair %s", clean)
		}
		if err := os.Rename(out+".partial", out); err != nil {
			return err
		}
	}
	return nil
}

func ensureStockfish(dest string, repair bool) (string, error) {
	bin := findStockfish(dest)
	if isStockfish19(bin) && !repair {
		say("Stockfish 19 verificado via UCI: %s", bin)
		return bin, nil
	}
	say("Baixando Stockfish 19 oficial (cerca de 81 MB)...")
	source := filepath.Join(dest, "downloads", "stockfish-19-windows-x64.zip")
	if repair {
		os.Remove(source)
	}
	if err := download(stockfishURL, source); err != nil {
		return "", fmt.Errorf("download do Stockfish falhou: %w", err)
	}
	if err := unpackZip(source, filepath.Join(dest, "engine")); err != nil {
		return "", err
	}
	bin = findStockfish(dest)
	if !isStockfish19(bin) {
		return "", errors.New("o executavel Stockfish 19 nao passou no teste UCI; confira CPU/antivirus")
	}
	say("Stockfish 19 pronto: %s", bin)
	return bin, nil
}

func scriptQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }

func copySelf(dest string) (string, error) {
	current, err := os.Executable()
	if err != nil {
		return "", err
	}
	target := filepath.Join(dest, "ChessVisionLab.exe")
	a, _ := filepath.Abs(current)
	b, _ := filepath.Abs(target)
	if strings.EqualFold(a, b) {
		return target, nil
	}
	src, err := os.Open(current)
	if err != nil {
		return "", err
	}
	defer src.Close()
	tmp := target + ".new"
	fp, err := os.Create(tmp)
	if err != nil {
		return "", err
	}
	_, err = io.Copy(fp, src)
	cErr := fp.Close()
	if err != nil {
		return "", err
	}
	if cErr != nil {
		return "", cErr
	}
	if err = os.Rename(tmp, target); err != nil {
		return "", err
	}
	return target, nil
}

func makeShortcuts(exe, dest string) {
	startMenu := filepath.Join(os.Getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs", "ChessVision Lab.lnk")
	// Optional convenience only; do not fail installation if policy blocks PowerShell.
	script := "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + scriptQuote(startMenu) + ");" +
		"$s.TargetPath=" + scriptQuote(exe) + ";" +
		"$s.WorkingDirectory=" + scriptQuote(dest) + ";" +
		"$s.Description='ChessVision Lab - Analisador local';$s.Save()"
	if err := runCommand(15*time.Second, dest, "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script); err != nil {
		say("Aviso: atalho do menu iniciar nao criado: %v", err)
	}
}

func openExtensionFolder(dest string) {
	folder := filepath.Join(dest, "extension")
	say("\nACAO MANUAL DO NAVEGADOR (uma unica vez):")
	say("  1. No Chrome: chrome://extensions  | Edge: edge://extensions")
	say("  2. Habilite Modo do desenvolvedor")
	say("  3. Selecione Carregar sem compactacao, pasta: %s", folder)
	if err := exec.Command("explorer.exe", folder).Start(); err != nil {
		say("Nao foi possivel abrir a pasta automaticamente: %v", err)
	}
}

func healthReady() bool {
	client := &http.Client{Timeout: 800 * time.Millisecond}
	resp, err := client.Get("http://127.0.0.1:8765/health")
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return false
	}
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 4096))
	return err == nil && bytes.Contains(raw, []byte("ChessVision Lab"))
}

func launchApp(dest, python string) error {
	if healthReady() {
		say("Ja existe uma instancia do ChessVision Lab ativa na porta 8765.")
		say("Se a janela nao aparecer, verifique as janelas abertas na barra de tarefas.")
		return nil
	}
	exe := filepath.Join(dest, ".venv", "Scripts", "pythonw.exe")
	if _, err := os.Stat(exe); err != nil {
		exe = python
	}
	logFile, err := os.OpenFile(filepath.Join(dest, "aplicativo.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}
	cmd := exec.Command(exe, "app.py")
	hideWindow(cmd)
	cmd.Dir = dest
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	cmd.Env = cleanPythonEnv(os.Environ())
	if err := cmd.Start(); err != nil {
		logFile.Close()
		return err
	}
	exited := make(chan error, 1)
	go func() { exited <- cmd.Wait(); logFile.Close() }()
	deadline := time.Now().Add(12 * time.Second)
	for time.Now().Before(deadline) {
		select {
		case err := <-exited:
			return fmt.Errorf("o programa terminou ao iniciar (%v). Consulte aplicativo.log", err)
		default:
		}
		if healthReady() {
			time.Sleep(700 * time.Millisecond)
			select {
			case err := <-exited:
				return fmt.Errorf("a interface fechou apos conectar (%v). Consulte aplicativo.log", err)
			default:
			}
			say("Interface iniciada (PID %d) e servidor localhost confirmado.", cmd.Process.Pid)
			return nil
		}
		time.Sleep(350 * time.Millisecond)
	}
	return errors.New("a interface nao ativou o servidor local. Consulte aplicativo.log e verifique se a porta 8765 esta em uso")
}

func run() error {
	repair := flag.Bool("reparar", false, "reinstala dependencias e Stockfish")
	diagnosis := flag.Bool("diagnostico", false, "somente testa a instalacao existente")
	extension := flag.Bool("extensao", false, "abre pasta da extensao")
	admin := flag.Bool("administrador", false, "executado pela central Electron")
	launchOnly := flag.Bool("abrir", false, "abre sem reinstalar")
	installOnly := flag.Bool("apenas-instalar", false, "instala sem abrir o aplicativo")
	selftest := flag.Bool("self-test", false, "testa arquivos incluidos no instalador (sem downloads)")
	flag.Parse()
	if *selftest {
		app, err := os.MkdirTemp("", "chessvision-selftest-")
		if err != nil {
			return err
		}
		defer os.RemoveAll(app)
		if err := embedExtract(app); err != nil {
			return err
		}
		for _, f := range []string{"app.py", "tracker.py", "variation_view.py", "extension/manifest.json", "diagnostico.py"} {
			if _, err := os.Stat(filepath.Join(app, filepath.FromSlash(f))); err != nil {
				return err
			}
		}
		fmt.Println("SELF-TEST OK - payload integrado e extraido")
		return nil
	}
	if runtime.GOOS != "windows" {
		return errors.New("necessario Windows x64")
	}
	dest, err := installPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dest, 0755); err != nil {
		return err
	}
	logfile, err := os.OpenFile(filepath.Join(dest, "instalacao.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err == nil {
		logger = io.MultiWriter(os.Stdout, logfile)
		defer logfile.Close()
	}
	say("CHESSVISION LAB 2.1 - INSTALACAO E REPARO AUTOMATICO TKINTER")
	say("Local: %s", dest)
	say("Log: %s", filepath.Join(dest, "instalacao.log"))
	if *launchOnly {
		// Atualiza a interface embutida mesmo quando o ambiente já está instalado.
		if err := embedExtract(dest); err != nil {
			return fmt.Errorf("nao foi possivel atualizar os arquivos do analisador: %w", err)
		}
		py := filepath.Join(dest, ".venv", "Scripts", "python.exe")
		if !venvValid(py) { return errors.New("ambiente Python invalido; instale ou repare pela central") }
		return launchApp(dest, py)
	}
	if *extension {
		openExtensionFolder(dest)
		return nil
	}
	if *diagnosis {
		py := filepath.Join(dest, ".venv", "Scripts", "python.exe")
		if !venvValid(py) {
			return errors.New("ambiente Python ausente; execute ChessVisionLab.exe para instalar")
		}
		stage(7, "Diagnostico completo")
		return runCommand(2*time.Minute, dest, py, "diagnostico.py")
	}
	firstInstall := false
	if _, err := os.Stat(filepath.Join(dest, ".venv", "Scripts", "python.exe")); err != nil {
		firstInstall = true
	}
	stage(1, "Arquivos do programa")
	if err := embedExtract(dest); err != nil {
		return err
	}
	say("Codigo, testes e extensao extraidos com sucesso.")
	stage(2, "Python 3 + teste REAL de janela Tkinter")
	py, err := ensurePython(dest)
	if err != nil {
		return err
	}
	stage(3, "Ambiente isolado e teste de janela")
	venv, err := ensureVenv(dest, py, *repair)
	if err != nil {
		return err
	}
	stage(4, "Motor Stockfish 19 - oficial")
	if _, err := ensureStockfish(dest, *repair); err != nil {
		return err
	}
	stage(5, "Integracao e testes reais")
	if err := runCommand(2*time.Minute, dest, venv, "diagnostico.py"); err != nil {
		return fmt.Errorf("diagnostico falhou (veja diagnostico_resultado.txt): %w", err)
	}
	stage(6, "Atalho e extensao Chrome/Edge")
	if !*admin {
	saved, err := copySelf(dest)
	if err != nil {
		say("Aviso: nao consegui criar copia permanente do instalador: %v", err)
	}
	if saved != "" {
		makeShortcuts(saved, dest)
	}
	if firstInstall {
		openExtensionFolder(dest)
	} else {
		say("Extensao ja extraida em: %s", filepath.Join(dest, "extension"))
	}
	} else {
		say("Extensao disponivel na central, pasta: %s", filepath.Join(dest, "extension"))
	}
	stage(7, "Abrir ChessVision Lab")
	if *installOnly {
		say("Instalacao concluida. Abra o atalho ChessVision Lab.")
		return nil
	}
	if err := launchApp(dest, venv); err != nil {
		return err
	}
	say("\nPrograma iniciado. Para diagnostico futuro: ChessVisionLab.exe -diagnostico")
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "\nERRO:", err)
		fmt.Fprintln(os.Stderr, "O log fica em %LOCALAPPDATA%\\ChessVisionLab\\instalacao.log")
		if runtime.GOOS == "windows" && len(os.Args) == 1 {
			fmt.Println("Pressione ENTER para fechar...")
			_, _ = fmt.Scanln()
		}
		os.Exit(1)
	}
}
