import requests
import csv
from datetime import datetime
import time
import json
import os

# ------------------- НАСТРОЙКИ --------------------
API_KEY = "xihUwmpfaHQ7Kyvk"  # замените на свой
INPUT_CSV = "input.csv"
OUTPUT_CSV = "output.csv"
FORECAST_DAYS = 14
SAVE_RESPONSES = True
RESPONSES_DIR = "responses"
# ------------------------------------------------

if SAVE_RESPONSES and not os.path.exists(RESPONSES_DIR):
    os.makedirs(RESPONSES_DIR)

def get_forecast(lat, lon, asl=None):
    packages = ["trend-day"]
    packages_str = "_".join(packages)
    url = f"https://my.meteoblue.com/packages/{packages_str}"
    params = {
        "apikey": API_KEY,
        "lat": lat,
        "lon": lon,
        "format": "json",
        "windspeed": "ms-1",
        "temperature": "C",
        "precipitationamount": "mm",
        "winddirection": "degree",
        "forecast_days": FORECAST_DAYS,
    }
    if asl is not None:
        params["asl"] = asl
    response = requests.get(url, params=params, timeout=30)
    if response.status_code != 200:
        raise Exception(f"API error {response.status_code}: {response.text}")
    return response.json()

def parse_date(date_str):
    return datetime.strptime(date_str, "%d.%m.%Y")

def save_response(data, name, date_str):
    if not SAVE_RESPONSES:
        return
    safe_name = name.replace(" ", "_").replace("/", "_")
    safe_date = date_str.replace(".", "-")
    filename = f"{safe_name}_{safe_date}.json"
    filepath = os.path.join(RESPONSES_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  💾 Ответ сохранён в {filepath}")

def extract_daily_data(data, target_date):
    daily = data.get("trend_day")
    if not daily:
        print("  Ответ не содержит 'trend_day'")
        return None, []
    times = daily.get("time")
    if not times:
        print("  В 'trend_day' нет поля 'time'")
        return None, []
    target_str = target_date.strftime("%Y-%m-%d")
    idx = -1
    for i, t in enumerate(times):
        if t.startswith(target_str):
            idx = i
            break
    if idx == -1:
        print(f"  Доступные даты (первые 10): {[t[:10] for t in times[:10]]}")
        return None, times
    result = {}
    for key, value in daily.items():
        if key == "time":
            continue
        if isinstance(value, list) and len(value) > idx:
            result[key] = value[idx]
        else:
            result[key] = None
    return result, times

def process_row(row):
    date_str = row["date"]
    lat = float(row["lat"])
    lon = float(row["lon"])
    height = row.get("height", "").strip()
    name = row.get("name", f"point_{lat}_{lon}")
    target_date = parse_date(date_str)
    asl = None
    if height:
        try:
            asl = float(height)
        except ValueError:
            pass
    print(f"Запрос для {name} ({lat}, {lon})...")
    try:
        data = get_forecast(lat, lon, asl)
        save_response(data, name, date_str)

        # ---- ДОБАВЛЯЕМ ВЫСОТУ ИЗ ОТВЕТА, ЕСЛИ ОНА ОТСУТСТВУЕТ ----
        if not height and "metadata" in data and "height" in data["metadata"]:
            row["height"] = data["metadata"]["height"]
            print(f"  📏 Высота из ответа: {row['height']} м")

        daily_info, _ = extract_daily_data(data, target_date)
        if daily_info is None:
            print(f"  ❌ Прогноз на {date_str} не найден")
        else:
            for key, value in daily_info.items():
                row[key] = value
            print(f"  ✅ Данные получены")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
    return row

def main():
    rows = []
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        base_fields = reader.fieldnames
        for row in reader:
            rows.append(row)

    processed = []
    all_fields = set(base_fields)
    for row in rows:
        processed_row = process_row(row)
        for key in processed_row.keys():
            all_fields.add(key)
        processed.append(processed_row)
        time.sleep(0.5)

    extra_fields = [f for f in all_fields if f not in base_fields]
    final_fieldnames = list(base_fields) + extra_fields

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=final_fieldnames, delimiter=";", extrasaction='ignore')
        writer.writeheader()
        writer.writerows(processed)

    print(f"\n✅ Готово! Результат сохранён в {OUTPUT_CSV}")
    if SAVE_RESPONSES:
        print(f"📁 Полные ответы сохранены в папке '{RESPONSES_DIR}'")

if __name__ == "__main__":
    main()