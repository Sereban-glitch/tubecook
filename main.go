// ============================================================================
// tubecook/main.go — Telegram HITL-бот оркестратора (agrobot-prod).
// HITL = Human-In-The-Loop: ни один ролик не уходит на YouTube без вашего
// одобрения. Бот только ДОСТАВЛЯЕТ решения, рендер выполняется на ноутбуке
// через TUBECOOK_RENDER_CMD (ssh или локально).
//
// Зависимости: НЕТ сторонних пакетов — только стандартная библиотека Go.
// Потребление: 15-30 МБ RAM, бинарник < 10 МБ (go build -ldflags="-s -w").
//
// Переменные окружения (.env / systemd Environment=):
//   TUBECOOK_TOKEN      — токен бота от @BotFather
//   TUBECOOK_ADMIN      — ваш chat_id (integer) — кому слать одобрения
//   TUBECOOK_JOBS       — каталог манифестов (по умолчанию ./jobs)
//   TUBECOOK_RENDER_CMD — команда рендера, {id} подставляется, напр.:
//                         "ssh user@hp-laptop 'cd ~/field-manual-scripts &&
//                          python3 06_render_short.py --manifest jobs/{id}.json'"
//   TUBECOOK_PREVIEW    — шаблон пути превью, {id} подставляется, напр.:
//                         "build/{id}/out/preview_270x480.mp4"
//
// Статусная машина (поле status в манифесте):
//   new -> sent -> approved -> rendering -> done
//                 -> skipped
//                 -> rework (ожидает текст правки) -> sent
// ============================================================================
package main

import (
        "bytes"
        "encoding/json"
        "fmt"
        "io"
        "log"
        "mime/multipart"
        "net/http"
        "os"
        "os/exec"
        "path/filepath"
        "strconv"
        "strings"
        "time"
)

// ---------------------------------------------------------------- конфиг --
type config struct {
        token     string
        admin     int64
        jobsDir   string
        renderCmd string
        preview   string
}

func loadConfig() config {
        c := config{
                token:     os.Getenv("TUBECOOK_TOKEN"),
                admin:     0,
                jobsDir:   envOr("TUBECOOK_JOBS", "jobs"),
                renderCmd: os.Getenv("TUBECOOK_RENDER_CMD"),
                preview:   envOr("TUBECOOK_PREVIEW", "build/{id}/out/preview_270x480.mp4"),
        }
        if v := os.Getenv("TUBECOOK_ADMIN"); v != "" {
                n, err := strconv.ParseInt(v, 10, 64)
                if err != nil {
                        log.Fatalf("TUBECOOK_ADMIN: %v", err)
                }
                c.admin = n
        }
        if c.token == "" || c.admin == 0 {
                log.Fatal("нужны TUBECOOK_TOKEN и TUBECOOK_ADMIN (см. .env.example)")
        }
        return c
}

func envOr(k, def string) string {
        if v := os.Getenv(k); v != "" {
                return v
        }
        return def
}

// ------------------------------------------------------------- манифесты --
// Работаем через map[string]any: НЕ теряем неизвестные поля манифеста
// (bgm, resolution и т.д.) при перезаписи статуса.
type job map[string]any

func jobPath(dir, id string) string { return filepath.Join(dir, id+".json") }

func readJob(dir, id string) (job, string, error) {
        raw, err := os.ReadFile(jobPath(dir, id))
        if err != nil {
                return nil, "", err
        }
        var j job
        if err := json.Unmarshal(raw, &j); err != nil {
                return nil, string(raw), err
        }
        return j, string(raw), nil
}

func (j job) str(k, def string) string {
        if v, ok := j[k].(string); ok {
                return v
        }
        return def
}

func (j job) id() string { return j.str("id", "") }

func saveJob(dir string, j job) error {
        raw, err := json.MarshalIndent(j, "", "  ")
        if err != nil {
                return err
        }
        return os.WriteFile(jobPath(dir, j.id()), raw, 0o644)
}

func set(j job, status, note string) {
        j["status"] = status
        j["note"] = note
        j["updated_at"] = time.Now().Format(time.RFC3339)
}

// --------------------------------------------------------------- Telegram --
var httpc = &http.Client{Timeout: 65 * time.Second}

func tg(c config, method string, payload any) (map[string]any, error) {
        body, _ := json.Marshal(payload)
        req, _ := http.NewRequest("POST",
                "https://api.telegram.org/bot"+c.token+"/"+method,
                bytes.NewReader(body))
        req.Header.Set("Content-Type", "application/json")
        resp, err := httpc.Do(req)
        if err != nil {
                return nil, err
        }
        defer resp.Body.Close()
        var out map[string]any
        if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
                return nil, err
        }
        if ok, _ := out["ok"].(bool); !ok {
                return out, fmt.Errorf("telegram %s: %v", method, out["description"])
        }
        return out, nil
}

// tgSendVideoFile — превью отправляем ФАЙЛОМ (не ссылкой): телеграм жмёт
// ссылки до 720p и убивает смысл HITL-проверки чёткости субтитров.
func tgSendVideoFile(c config, path, caption string) (int64, error) {
        f, err := os.Open(path)
        if err != nil {
                return 0, err
        }
        defer f.Close()

        buf := &bytes.Buffer{}
        w := multipart.NewWriter(buf)
        _ = w.WriteField("chat_id", strconv.FormatInt(c.admin, 10))
        _ = w.WriteField("caption", caption)
        part, _ := w.CreateFormFile("video", filepath.Base(path))
        if _, err = io.Copy(part, f); err != nil {
                return 0, err
        }
        w.Close()

        req, _ := http.NewRequest("POST",
                "https://api.telegram.org/bot"+c.token+"/sendVideo", buf)
        req.Header.Set("Content-Type", w.FormDataContentType())
        resp, err := httpc.Do(req)
        if err != nil {
                return 0, err
        }
        defer resp.Body.Close()
        var out struct {
                OK     bool           `json:"ok"`
                Result map[string]any `json:"result"`
        }
        if err = json.NewDecoder(resp.Body).Decode(&out); err != nil {
                return 0, err
        }
        if !out.OK {
                return 0, fmt.Errorf("sendVideo отклонён")
        }
        if msg, ok := out.Result["message_id"].(float64); ok {
                return int64(msg), nil
        }
        return 0, nil
}

func tgText(c config, text string, keyboard [][]map[string]string) {
        payload := map[string]any{
                "chat_id": c.admin, "text": text, "parse_mode": "HTML",
        }
        if keyboard != nil {
                payload["reply_markup"] = map[string]any{"inline_keyboard": keyboard}
        }
        if _, err := tg(c, "sendMessage", payload); err != nil {
                log.Printf("[tg] sendMessage: %v", err)
        }
}

func approveKeyboard(id string) [][]map[string]string {
        return [][]map[string]string{{
                {"text": "APPROVE", "callback_data": "approve:" + id},
                {"text": "SKIP", "callback_data": "skip:" + id},
                {"text": "REWORK", "callback_data": "rework:" + id},
        }}
}

// ------------------------------------------------------- отправка на рендер --
func renderAndReport(c config, j job) {
        id := j.id()
        set(j, "rendering", "")
        _ = saveJob(c.jobsDir, j)

        cmd := strings.ReplaceAll(c.renderCmd, "{id}", id)
        tgText(c, fmt.Sprintf("RENDER <b>%s</b>\n<code>%s</code>", id, cmd), nil)
        out, err := exec.Command("sh", "-c", cmd).CombinedOutput()
        tail := string(out)
        if len(tail) > 1200 {
                tail = "..." + tail[len(tail)-1200:]
        }

        if err != nil {
                set(j, "failed", tail)
                _ = saveJob(c.jobsDir, j)
                tgText(c, fmt.Sprintf("FAIL <b>%s</b>\n<pre>%s</pre>", id, tail), nil)
                return
        }
        set(j, "done", tail)
        _ = saveJob(c.jobsDir, j)
        tgText(c, fmt.Sprintf("DONE <b>%s</b>\nРучная выгрузка: 07_upload_youtube.py или ждите квоту.\n<pre>%s</pre>", id, tail), nil)
}

func trySendPreview(c config, j job) {
        id := j.id()
        prev := strings.ReplaceAll(c.preview, "{id}", id)
        if _, err := os.Stat(prev); err == nil {
                caption := fmt.Sprintf("HITL %s — «%s»\nГолос: %s",
                        id, j.str("title", "?"), j.str("voice", "edge-tts"))
                if _, err := tgSendVideoFile(c, prev, caption); err != nil {
                        tgText(c, "превью не отправилось файлом ("+err.Error()+"), проверьте вручную: "+prev, nil)
                }
        } else {
                tgText(c, "превью не найдено: "+prev, nil)
        }
}

// ------------------------------------------------------------- колбэки ----
func handleCallback(c config, cb map[string]any) {
        idata, _ := cb["data"].(string)
        from, _ := cb["from"].(map[string]any)
        var chatID float64
        if from != nil {
                if u, ok := from["id"].(float64); ok {
                        chatID = u
                }
        }
        if int64(chatID) != c.admin { // чужой нажал кнопку — игнор
                return
        }
        parts := strings.SplitN(idata, ":", 2)
        if len(parts) != 2 {
                return
        }
        action, id := parts[0], parts[1]
        j, _, err := readJob(c.jobsDir, id)
        if err != nil {
                return
        }

        switch action {
        case "approve":
                set(j, "approved", "")
                _ = saveJob(c.jobsDir, j)
                tgAnswerCallback(c, cb, "Одобрено — запускаю рендер")
                go renderAndReport(c, j) // асинхронно: рендер минутного масштаба
        case "skip":
                set(j, "skipped", "")
                _ = saveJob(c.jobsDir, j)
                tgAnswerCallback(c, cb, "Скипнут — в архив")
        case "rework":
                set(j, "rework", "")
                _ = saveJob(c.jobsDir, j)
                tgAnswerCallback(c, cb, "Опишите правку следующим сообщением")
                tgText(c, "Опишите правку для "+id+" (одним сообщением):", nil)
        }
}

func tgAnswerCallback(c config, cb map[string]any, text string) {
        payload := map[string]any{"callback_query_id": cb["id"], "text": text}
        if _, err := tg(c, "answerCallbackQuery", payload); err != nil {
                log.Printf("[tg] answerCallbackQuery: %v", err)
        }
}

// ------------------------------------------------------------ текст правки --
func handleMessage(c config, msg map[string]any) {
        chat, _ := msg["chat"].(map[string]any)
        if chat == nil {
                return
        }
        if cid, _ := chat["id"].(float64); int64(cid) != c.admin {
                return
        }
        text, _ := msg["text"].(string)
        if !strings.HasPrefix(text, "/") {
                // это ответ на REWORK: ищем единственную задачу в статусе rework
                entries, _ := os.ReadDir(c.jobsDir)
                for _, e := range entries {
                        if !strings.HasSuffix(e.Name(), ".json") {
                                continue
                        }
                        id := strings.TrimSuffix(e.Name(), ".json")
                        j, _, err := readJob(c.jobsDir, id)
                        if err != nil {
                                continue
                        }
                        if j.str("status", "") == "rework" {
                                set(j, "new", text)
                                _ = saveJob(c.jobsDir, j)
                                tgText(c, "Правка принята, задача "+id+" снова в очереди.", nil)
                                offerJob(c, j)
                                return
                        }
                }
                tgText(c, "Жду команду /queue или текст правки (после REWORK).", nil)
                return
        }
        switch text {
        case "/queue", "/start":
                scanAndOffer(c)
        default:
                tgText(c, "Команды: /queue — разослать новую партию. " +
                        "Кнопки: APPROVE / SKIP / REWORK.", nil)
        }
}

// -------------------------------------------------------------- очередь ----
func offerJob(c config, j job) {
        id := j.id()
        title, hook := j.str("title", "?"), j.str("hook", "")
        sc := "нет"
        if v, ok := j["scene_seconds"].([]any); ok {
                nums := make([]string, len(v))
                for i, x := range v {
                        if f, ok := x.(float64); ok {
                                nums[i] = strconv.Itoa(int(f))
                        }
                }
                sc = strings.Join(nums, "+") + " c"
        }
        text := fmt.Sprintf(
                "<b>%s</b>\nХук: %s\nСцены: %s | Голос: %s\n<b>%s</b>",
                title, hook, sc, j.str("voice", "ru-RU-DmitryNeural"), id)
        set(j, "sent", "")
        _ = saveJob(c.jobsDir, j)
        tgText(c, text, approveKeyboard(id))
        trySendPreview(c, j)
}

func scanAndOffer(c config) {
        entries, err := os.ReadDir(c.jobsDir)
        if err != nil {
                log.Fatalf("[jobs] %v", err)
        }
        n := 0
        for _, e := range entries {
                if !strings.HasSuffix(e.Name(), ".json") {
                        continue
                }
                id := strings.TrimSuffix(e.Name(), ".json")
                j, _, err := readJob(c.jobsDir, id)
                if err != nil {
                        log.Printf("[jobs] %s: %v", id, err)
                        continue
                }
                if j.str("status", "") == "new" {
                        offerJob(c, j)
                        n++
                }
        }
        tgText(c, fmt.Sprintf("Партия: %d новых задач.", n), nil)
}

// ------------------------------------------------------------------ main --
func main() {
        c := loadConfig()
        log.Printf("[tubecook] админ=%d jobs=%s", c.admin, c.jobsDir)

        // приветственная партия при старте
        go scanAndOffer(c)

        offset := 0
        for {
                u, err := tg(c, "getUpdates", map[string]any{
                        "offset": offset, "timeout": 50, "allowed_updates": []string{"message", "callback_query"},
                })
                if err != nil {
                        log.Printf("[poll] %v (повтор через 5 c)", err)
                        time.Sleep(5 * time.Second)
                        continue
                }
                updates, _ := u["result"].([]any)
                for _, up := range updates {
                        m, _ := up.(map[string]any)
                        if id, ok := m["update_id"].(float64); ok {
                                offset = int(id) + 1
                        }
                        if cb, ok := m["callback_query"].(map[string]any); ok {
                                handleCallback(c, cb)
                        }
                        if msg, ok := m["message"].(map[string]any); ok {
                                handleMessage(c, msg)
                        }
                }
        }
}
