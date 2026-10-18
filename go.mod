module tubecook

go 1.27

// Сторонних зависимостей НЕТ — только стандартная библиотека.
// Сборка (на agrobot-prod):
//   go build -trimpath -ldflags="-s -w" -o /usr/local/bin/tubecook ./tubecook
// Результат: бинарник ~7 МБ, RSS 15-30 МБ.
