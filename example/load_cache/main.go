package main

import (
	"context"
	"fmt"
	"log"
	"math"
	"math/rand"
	"os"
	"sync"

	"github.com/go-resty/resty/v2"
	"github.com/redis/go-redis/v9"
)

// Переводит широту/долготу в координаты тайла OSM на заданном зуме.
// Возвращает (x, y).
func tileIndexesByCoords(lat, lon, zoom float64) (int, int) {

	lat_rad := lat * (math.Pi / 180)
	n := math.Pow(2, zoom)

	x := (lon + 180.0) / 360.0 * n
	y := n * (1.0 - math.Log(math.Tan(lat_rad)+1.0/math.Cos(lat_rad))/math.Pi) / 2.0

	return int(math.Floor(x)), int(math.Floor(y))
}

func tilesForBoundingBox(lat_min, lon_min, lat_max, lon_max, zoom float64) [][]int {

	// Считаем индексы для углов
	x1, y1 := tileIndexesByCoords(lat_min, lon_min, zoom)
	x2, y2 := tileIndexesByCoords(lat_min, lon_max, zoom)
	x3, y3 := tileIndexesByCoords(lat_max, lon_min, zoom)
	x4, y4 := tileIndexesByCoords(lat_max, lon_max, zoom)

	// Выбираем границы
	x_min_t := min(x1, x2, x3, x4)
	x_max_t := max(x1, x2, x3, x4)
	y_min_t := min(y1, y2, y3, y4)
	y_max_t := max(y1, y2, y3, y4)

	// Обрезаем по валидному диапазону
	max_index := math.Pow(2, zoom) - 1

	x_min_t = max(0, x_min_t)
	x_max_t = min(int(max_index), x_max_t)
	y_min_t = max(0, y_min_t)
	y_max_t = min(int(max_index), y_max_t)

	tiles := [][]int{}

	for x := int(x_min_t); x <= int(x_max_t); x++ {
		for y := int(y_min_t); y <= int(y_max_t); y++ {
			tiles = append(tiles, []int{x, y})
		}
	}

	return tiles
}

var ctx = context.Background()

func main() {
	rdb := redis.NewClient(&redis.Options{
		Addr: os.Getenv("REDIS_SERVER"),
		DB:   0,
	})

	// нижняя граница (южнее, западнее)
	lat_min, lon_min := 55.412846, 36.840232

	// верхняя граница (севернее, восточнее)
	lat_max, lon_max := 56.340303, 38.238225

	for zoom := 1; zoom <= 19; zoom++ {

		allTiles := tilesForBoundingBox(lat_min, lon_min, lat_max, lon_max, float64(zoom))

		randomOSMURL := func(x, y, z int) string {
			osm_url := []string{
				fmt.Sprintf("https://tile.openstreetmap.org/%d/%d/%d.png", z, x, y),
				fmt.Sprintf("https://a.tile.openstreetmap.org/%d/%d/%d.png", z, x, y),
				fmt.Sprintf("https://b.tile.openstreetmap.org/%d/%d/%d.png", z, x, y),
				fmt.Sprintf("https://c.tile.openstreetmap.org/%d/%d/%d.png", z, x, y),
			}
			return osm_url[rand.Intn(len(osm_url))]
		}

		client := resty.New()

		client.SetHeaders(map[string]string{
			"User-Agent": "OSM-Viewer/1.0 (contact@example.com)",
		})

		// Семафор для ограничения числа параллельных горутин (например, 10 одновременно)
		const maxGoroutines = 2
		sem := make(chan struct{}, maxGoroutines)

		// Механизм синхронизации
		var wg sync.WaitGroup

		// Чтобы эффективно делать записи в Redis, можно собрать результаты в канал
		// и записывать их пачками через pipeline.
		type tileData struct {
			key  string
			data []byte
		}

		tilesChan := make(chan tileData, 1000) // буфер подстраиваем под объём
		defer close(tilesChan)

		// Запускаем фон-воркер, который принимает готовые данные и пакетно кладёт в Redis
		go func() {
			defer close(tilesChan)
			pipeline := rdb.Pipeline()
			counter := 0

			for td := range tilesChan {
				pipeline.Set(ctx, td.key, td.data, 0)
				counter++

				// Периодически отправляем пачку (например, по 100 штук)
				if counter >= 100 {
					if _, err := pipeline.Exec(ctx); err != nil {
						log.Printf("Ошибка pipeline: %v", err)
					}
					counter = 0
				}
			}
			// В конце не забываем «слить» последние записи
			if counter > 0 {
				if _, err := pipeline.Exec(ctx); err != nil {
					log.Printf("Ошибка pipeline: %v", err)
				}
			}
		}()

		// Перебираем все тайлы и запускаем горутины
		for _, coords := range allTiles {
			wg.Add(1)
			sem <- struct{}{} // занять «слот»
			go func(coords []int) {
				defer wg.Done()
				defer func() { <-sem }() // освободить «слот» в семафоре

				x := int(coords[0])
				y := int(coords[1])
				tileName := fmt.Sprintf("tile_%d_%d_%d", x, y, zoom)

				// Проверяем, есть ли уже в Redis
				_, err := rdb.Get(ctx, tileName).Result()
				if err != redis.Nil {
					// Если err == nil, значит тайл уже есть
					// Если err != redis.Nil и != nil, это ошибка соединения и т.п.
					// Для простоты пропустим ошибку, либо залогируем:
					// log.Println("Ошибка Redis:", err)
					// или проверим, действительно ли это «уже есть»
					if err == nil {
						fmt.Printf("Box %s уже загружен\n", tileName)
					} else {
						log.Printf("Redis Get для %s завершился ошибкой: %v\n", tileName, err)
					}
					return
				}

				// Грузим тайл
				url := randomOSMURL(x, y, zoom)
				resp, err := client.R().Get(url)
				if err != nil {
					log.Printf("Ошибка http-запроса для %s: %v", tileName, err)
					return
				}

				// Отправляем в канал для записи в Redis (пакетная запись)
				tilesChan <- tileData{
					key:  tileName,
					data: resp.Body(),
				}

				fmt.Printf("Загрузили тайл %s\n", tileName)
			}(coords)
		}

		// Ждём окончания всех загрузок
		wg.Wait()
	}

}
