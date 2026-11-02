#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Универсальный анализатор погоды для велопохода.
Собирает точки маршрута, запрашивает историческую погоду за указанные годы,
строит CSV и интерактивный HTML-дашборд.
Дополнительно: получает высоты, дедуплицирует точки, объединяет с GPX-файлами,
приводит населённые пункты к верхнему регистру и сортирует данные по дате.
"""

import os
import re
import time
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

# ============================================================
#  НАСТРОЙКИ (меняйте под свой поход)
# ============================================================

# ---- Какие годы анализировать ----
YEARS = [2024, 2025]

# ---- Какие часы брать (местное время) ----
HOURS = [0, 9, 13, 18]

# ---- Часовой пояс (для запросов к Open-Meteo) ----
# Возможные значения: список IANA time zones.
# Примеры: "Asia/Tokyo", "Europe/Moscow", "America/New_York", "Europe/London", "UTC".
# Полный список: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
TIMEZONE = "Asia/Tokyo"   # <-- измените на свой

# ---- Пути к файлам ----
INPUT_DIR = "input/"
OUTPUT_DIR = "output/"

PLAN_FILE = "План похода Тянь-Шань 2026.md"
CAMPS_FILE = "ночевки.txt"
VILLAGES_FILE = "населенка.txt"
PASSES_FILE = "ПП.txt"

# ---- Если у вас уже есть готовый CSV с колонками:
#      date, name, type, lat, lon, height
#      раскомментируйте строку ниже и укажите путь к нему.
#      Тогда скрипт пропустит парсинг и сразу перейдет к запросу погоды.
EXISTING_CSV = "input/points_full.csv"

# ---- Дополнительный GPX с точками для погоды (например, Погода_Япония.txt) ----
#      Если файл существует, скрипт создаст отдельный CSV с их высотами.
#      Укажите None или закомментируйте, если не нужен.
WEATHER_POINTS_GPX = "input/Погода_Япония.txt"

# ---- Дополнительный CSV с точками (без дат) для объединения с основным маршрутом ----
#      Например, weather_points_with_elevation.csv, созданный из WEATHER_POINTS_GPX.
#      Скрипт автоматически назначит даты этим точкам (продолжая с последней даты
#      из основного набора) или запросит начальную дату, если дат нет.
WEATHER_POINTS_CSV = "output/weather_points_with_elevation.csv"

# ---- Тип точки по умолчанию для дополнительных точек (если в CSV нет колонки 'type') ----
DEFAULT_TYPE = "населённый пункт"

# ---- Автоматически назначать даты дополнительным точкам ----
#      True – продолжить с последней даты основного набора;
#      False – запросить начальную дату у пользователя.
AUTO_DATE_FROM_LAST = True

# ---- Точность округления координат для дедупликации ----
DEDUP_ROUND_DIGITS = 5

# ============================================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def parse_gpx(file_path, name_field='name'):
    """Извлекает из GPX точки с координатами и названиями."""
    if not os.path.exists(file_path):
        return []
    tree = ET.parse(file_path)
    root = tree.getroot()
    ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
    points = []
    for wpt in root.findall('gpx:wpt', ns):
        lat = float(wpt.get('lat'))
        lon = float(wpt.get('lon'))
        name_elem = wpt.find('gpx:name', ns)
        name = name_elem.text if name_elem is not None else ''
        points.append({'name': name.strip(), 'lat': lat, 'lon': lon})
    return points

def parse_plan_md(file_path):
    """Извлекает из Markdown-плана высоты и типы точек."""
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    points = []
    pattern = r'мс\d+[:：]\s*(.+?)\s*\((\d+)\s*м\)'
    for name, height in re.findall(pattern, text):
        points.append({'name': name.strip(), 'height': int(height), 'type': 'ночёвка'})
    pattern_pass = r'Пер\.\s*(.+?)\s*\((\d+)\s*м\)'
    for name, height in re.findall(pattern_pass, text):
        if not any(p['name'] == name for p in points):
            points.append({'name': 'Пер. ' + name.strip(), 'height': int(height), 'type': 'перевал'})
    return points

def get_elevation(lat, lon):
    """Запрашивает высоту через Open-Meteo Elevation API."""
    url = "https://api.open-meteo.com/v1/elevation"
    try:
        resp = requests.get(url, params={"latitude": lat, "longitude": lon}, timeout=5)
        resp.raise_for_status()
        return resp.json().get('elevation', [None])[0]
    except:
        return None

def get_historical_weather(lat, lon, year, month, day, hours, elevation=None):
    """Запрашивает почасовые данные для указанной даты и года."""
    date_str = f"{year}-{month:02d}-{day:02d}"
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date_str,
        "end_date": date_str,
        "hourly": "temperature_2m,precipitation,wind_speed_10m",
        "timezone": TIMEZONE,
        "models": "ecmwf_ifs"
    }
    if elevation is not None:
        params["elevation"] = elevation
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        hourly = data.get('hourly', {})
        times = hourly.get('time', [])
        temps = hourly.get('temperature_2m', [])
        precips = hourly.get('precipitation', [])
        winds = hourly.get('wind_speed_10m', [])
        result = {}
        for t, tmp, pr, w in zip(times, temps, precips, winds):
            hour = int(t[11:13])
            if hour in hours:
                result[hour] = (tmp, pr, w)
        return result
    except Exception as e:
        print(f"Ошибка запроса {date_str}: {e}")
        return {}

# ============================================================
#  СБОР ТАБЛИЦЫ ТОЧЕК ИЗ ФАЙЛОВ
# ============================================================

def build_point_table(plan_file, camps_file, villages_file, passes_file):
    """Собирает таблицу точек из GPX-файлов и плана."""
    camps = parse_gpx(camps_file)
    villages = parse_gpx(villages_file)
    passes = parse_gpx(passes_file)
    plan_info = parse_plan_md(plan_file)
    info_by_name = {p['name']: p for p in plan_info}

    rows = []
    # Ночёвки
    for p in camps:
        name = p['name']
        info = info_by_name.get(name, {})
        date_match = re.search(r'мс(\d{2})-(\d{2})', name)
        if date_match:
            date_str = f"{date_match.group(1)}.{date_match.group(2)}.2026"
        else:
            date_str = None
        rows.append({
            'date': date_str,
            'name': name,
            'type': info.get('type', 'ночёвка'),
            'lat': p['lat'],
            'lon': p['lon'],
            'height': info.get('height')
        })
    # Населенные пункты – сразу в верхнем регистре
    for p in villages:
        if any(r['name'] == p['name'] for r in rows):
            continue
        rows.append({
            'date': None,
            'name': p['name'].strip().upper(),
            'type': 'населённый пункт',
            'lat': p['lat'],
            'lon': p['lon'],
            'height': None
        })
    # Перевалы
    for p in passes:
        if any(r['name'] == p['name'] for r in rows):
            continue
        info = info_by_name.get(p['name'], {})
        rows.append({
            'date': None,
            'name': p['name'],
            'type': info.get('type', 'перевал'),
            'lat': p['lat'],
            'lon': p['lon'],
            'height': info.get('height')
        })
    # Запрашиваем недостающие высоты
    for row in rows:
        if row['height'] is None and row['lat'] is not None and row['lon'] is not None:
            elev = get_elevation(row['lat'], row['lon'])
            if elev is not None:
                row['height'] = round(elev, 1)
                print(f"Высота для {row['name']}: {row['height']} м")
            time.sleep(0.2)
    df = pd.DataFrame(rows)
    df = df[df['lat'].notna() & df['lon'].notna()]
    return df

# ============================================================
#  ОЧИСТКА И ДЕДУПЛИКАЦИЯ
# ============================================================

def clean_and_deduplicate(df, round_digits=5):
    """
    Приводит названия населённых пунктов к верхнему регистру
    и удаляет дубли по координатам (с округлением).
    """
    if 'type' in df.columns:
        mask = df['type'] == 'населённый пункт'
        df.loc[mask, 'name'] = df.loc[mask, 'name'].astype(str).str.strip().str.upper()

    if 'lat' in df.columns and 'lon' in df.columns:
        df['_key'] = df['lat'].round(round_digits).astype(str) + '_' + df['lon'].round(round_digits).astype(str)
        df_sorted = df.sort_values(by='height', na_position='last', ascending=False)
        df_clean = df_sorted.drop_duplicates(subset='_key', keep='first')
        df_clean = df_clean.drop(columns=['_key'])
        print(f"Дедупликация: удалено {len(df) - len(df_clean)} дублирующихся точек.")
        return df_clean
    else:
        print("ВНИМАНИЕ: не найдены колонки lat/lon, дедупликация не выполнена.")
        return df

# ============================================================
#  ОБРАБОТКА ДОПОЛНИТЕЛЬНЫХ ТОЧЕК
# ============================================================

def process_weather_points(gpx_path, output_dir):
    """Извлекает точки из GPX, запрашивает высоты и сохраняет CSV."""
    points = parse_gpx(gpx_path)
    if not points:
        print("Файл с точками погоды не найден или пуст.")
        return None
    rows = []
    for p in points:
        elev = get_elevation(p['lat'], p['lon'])
        if elev is not None:
            elev = round(elev, 1)
        rows.append({
            'name': p['name'].strip().upper(),
            'lat': p['lat'],
            'lon': p['lon'],
            'height': elev
        })
        print(f"{p['name']}: {elev} м" if elev is not None else f"{p['name']}: высота не получена")
        time.sleep(0.3)
    df = pd.DataFrame(rows)
    csv_path = os.path.join(output_dir, 'weather_points_with_elevation.csv')
    df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=';')
    print(f"✅ CSV с высотами для точек погоды сохранён: {csv_path}")
    return csv_path

def merge_weather_points(df_main, weather_csv, default_type, auto_date=True):
    """
    Загружает дополнительный CSV, добавляет даты (если их нет)
    и объединяет с основным DataFrame.
    """
    if not os.path.exists(weather_csv):
        return df_main

    df_extra = pd.read_csv(weather_csv, encoding='utf-8-sig', sep=';')
    for col in ['name', 'lat', 'lon']:
        if col not in df_extra.columns:
            print(f"Ошибка: в {weather_csv} отсутствует колонка '{col}'")
            return df_main

    if 'type' not in df_extra.columns:
        df_extra['type'] = default_type
    if 'height' not in df_extra.columns:
        df_extra['height'] = None

    df_extra['name'] = df_extra['name'].astype(str).str.strip().str.upper()

    has_date = 'date' in df_extra.columns and not df_extra['date'].isna().all()
    if not has_date:
        print("В дополнительном файле нет дат. Назначаем даты...")
        last_date = None
        if not df_main.empty and 'date' in df_main.columns:
            dates_main = df_main['date'].dropna()
            if not dates_main.empty:
                try:
                    last_date = max(dates_main.apply(lambda x: datetime.strptime(x, "%d.%m.%Y")))
                except Exception:
                    pass

        if last_date is not None and auto_date:
            print(f"Автоматическое назначение дат, начиная с {last_date.strftime('%d.%m.%Y')} + 1 день")
            new_dates = []
            current = last_date + timedelta(days=1)
            for _ in range(len(df_extra)):
                new_dates.append(current.strftime("%d.%m.%Y"))
                current += timedelta(days=1)
            df_extra['date'] = new_dates
        else:
            print("В основном наборе нет дат или AUTO_DATE_FROM_LAST = False.")
            start_str = input("Введите начальную дату в формате ДД.ММ.ГГГГ (например, 01.01.2025): ")
            try:
                start_date = datetime.strptime(start_str, "%d.%m.%Y")
            except Exception:
                print("Некорректный формат. Использую сегодняшнюю дату.")
                start_date = datetime.now()
            new_dates = []
            current = start_date
            for _ in range(len(df_extra)):
                new_dates.append(current.strftime("%d.%m.%Y"))
                current += timedelta(days=1)
            df_extra['date'] = new_dates

    df_combined = pd.concat([df_main, df_extra], ignore_index=True)
    print(f"Добавлено {len(df_extra)} точек из {weather_csv}. Всего точек: {len(df_combined)}")
    return df_combined

# ============================================================
#  ЗАПРОС ПОГОДЫ
# ============================================================

def fetch_weather_for_df(df, years, hours):
    """Добавляет в DataFrame колонки с погодой для каждого года и часа."""
    for year in years:
        for hour in hours:
            df[f't{hour}_{year}'] = None
            df[f'p{hour}_{year}'] = None
            df[f'w{hour}_{year}'] = None

    for idx, row in df.iterrows():
        if pd.isna(row['date']):
            print(f"Пропускаем {row['name']} – нет даты")
            continue
        try:
            date_obj = datetime.strptime(str(row['date']), "%d.%m.%Y")
        except Exception:
            continue
        day, month = date_obj.day, date_obj.month
        lat, lon = row['lat'], row['lon']
        elev = row['height'] if not pd.isna(row['height']) else None

        for year in years:
            print(f"Запрос {row['name']} {row['date']} за {year}...")
            hour_data = get_historical_weather(lat, lon, year, month, day, hours, elev)
            for h in hours:
                if h in hour_data:
                    tmp, pr, w = hour_data[h]
                    df.at[idx, f't{h}_{year}'] = round(tmp, 1) if tmp is not None else None
                    df.at[idx, f'p{h}_{year}'] = round(pr, 1) if pr is not None else None
                    df.at[idx, f'w{h}_{year}'] = round(w, 1) if w is not None else None
            time.sleep(0.5)
        time.sleep(0.3)

    # Min/max по годам для каждого часа
    for hour in hours:
        t_cols = [f't{hour}_{year}' for year in years]
        p_cols = [f'p{hour}_{year}' for year in years]
        w_cols = [f'w{hour}_{year}' for year in years]
        df[f't{hour}_min'] = df[t_cols].min(axis=1)
        df[f't{hour}_max'] = df[t_cols].max(axis=1)
        df[f'p{hour}_min'] = df[p_cols].min(axis=1)
        df[f'p{hour}_max'] = df[p_cols].max(axis=1)
        df[f'w{hour}_min'] = df[w_cols].min(axis=1)
        df[f'w{hour}_max'] = df[w_cols].max(axis=1)
    return df

# ============================================================
#  ДАШБОРД
# ============================================================

def generate_dashboard_from_df(df, output_html, output_csv=None):
    """Генерирует интерактивный HTML-дашборд из DataFrame."""
    if output_csv:
        df.to_csv(output_csv, index=False, encoding='utf-8-sig', sep=';')
        print(f"CSV сохранён: {output_csv}")

    df_clean = df[df['date'].notna()].copy()
    if df_clean.empty:
        print("Нет данных с датами, дашборд не будет построен.")
        return

    df_clean['date_sort'] = df_clean['date'].apply(lambda x: datetime.strptime(str(x), "%d.%m.%Y"))
    df_clean = df_clean.sort_values('date_sort').drop('date_sort', axis=1)

    dates = sorted(df_clean['date'].unique(), key=lambda x: datetime.strptime(str(x), "%d.%m.%Y"))

    # ---- Динамические типы из CSV ----
    if 'type' in df_clean.columns:
        types = sorted([str(t).strip() for t in df_clean['type'].dropna().unique() if str(t).strip()])
    else:
        types = []

    points = sorted(df_clean['name'].unique())
    df_json = df_clean.to_json(orient='records', force_ascii=False)

    hours = [0, 9, 13, 18]
    html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Погода на маршруте</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; }}
        .filters {{ display: flex; gap: 15px; margin-bottom: 20px; align-items: center; flex-wrap: wrap; }}
        .filters label {{ font-weight: bold; }}
        .filters select {{ padding: 6px 10px; font-size: 14px; border-radius: 4px; border: 1px solid #ccc; }}
        .charts {{ display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }}
        .chart-container {{ flex: 1 1 45%; min-width: 300px; height: 400px; }}
        .table-container {{ overflow-x: auto; margin-top: 20px; }}
        table {{ border-collapse: collapse; font-size: 12px; width: 100%; }}
        th {{ background-color: #4CAF50; color: white; padding: 6px; border: 1px solid #ddd; position: sticky; top: 0; }}
        td {{ padding: 4px 6px; border: 1px solid #ddd; text-align: center; }}
        .legend {{ display: flex; gap: 20px; margin-bottom: 10px; flex-wrap: wrap; }}
        .legend-item {{ display: flex; align-items: center; gap: 5px; }}
        .color-box {{ width: 20px; height: 20px; border: 1px solid #888; }}
        .note {{ margin-top: 20px; font-size: 14px; color: #555; }}
        .reset-btn {{ padding: 6px 14px; background: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer; }}
        .reset-btn:hover {{ background: #d32f2f; }}
    </style>
</head>
<body>
<div class="container">
    <h1>🌦️ Погода на маршруте</h1>
    <div class="legend">
        <div class="legend-item"><span class="color-box" style="background-color: #b3d9ff;"></span> Холодно (t < 5°C)</div>
        <div class="legend-item"><span class="color-box" style="background-color: #ffffb3;"></span> Умеренно (5–25°C)</div>
        <div class="legend-item"><span class="color-box" style="background-color: #ffb3b3;"></span> Жарко (t > 25°C)</div>
        <div class="legend-item"><span class="color-box" style="background-color: #b3d9ff; border: 2px solid #0099ff;"></span> Осадки > 0</div>
        <div class="legend-item"><span class="color-box" style="background-color: #ffcc66;"></span> Ветер > 10 м/с</div>
        <div class="legend-item"><span class="color-box" style="background-color: #ff9999;"></span> Ветер > 15 м/с</div>
    </div>
    <div class="filters">
        <label for="dateSelect">Дата:</label>
        <select id="dateSelect"><option value="">-- все даты --</option>
        {''.join(f'<option value="{d}">{d}</option>' for d in dates)}
        </select>
        <label for="typeFilter">Тип:</label>
        <select id="typeFilter">
            <option value="all">Все</option>
            {''.join(f'<option value="{t}">{t}</option>' for t in types)}
        </select>
        <label for="pointSelect">Точка:</label>
        <select id="pointSelect"><option value="">-- все точки --</option>
        {''.join(f'<option value="{p}">{p}</option>' for p in points)}
        </select>
        <button class="reset-btn" onclick="resetFilters()">Сбросить</button>
    </div>
    <div class="charts">
        <div class="chart-container" id="tempChart"></div>
        <div class="chart-container" id="precipWindChart"></div>
    </div>
    <div class="table-container" id="tableContainer"></div>
    <div class="note">* t — температура (°C), p — осадки (мм), w — ветер (м/с). Показаны min и max за указанные годы.</div>
</div>
<script>
    const data = {df_json};
    const allDates = {json.dumps(dates, ensure_ascii=False)};
    const hours = {json.dumps(hours)};

    function getTempColor(t) {{
        if (t === null || t === undefined || isNaN(t)) return '';
        if (t < 5) return 'background-color: #b3d9ff;';
        if (t > 25) return 'background-color: #ffb3b3;';
        return 'background-color: #ffffb3;';
    }}
    function getPrecipColor(p) {{
        if (p > 0) return 'background-color: #b3d9ff;';
        return '';
    }}
    function getWindColor(w) {{
        if (w > 15) return 'background-color: #ff9999;';
        if (w > 10) return 'background-color: #ffcc66;';
        return '';
    }}

    function renderTable(filteredData) {{
        let html = `<table><thead><tr><th>Дата</th><th>Точка</th><th>Тип</th><th>Высота</th>
            <th colspan="6">0:00</th><th colspan="6">9:00</th><th colspan="6">13:00</th><th colspan="6">18:00</th>
        </tr><tr><th></th><th></th><th></th><th></th>
            <th>t min</th><th>t max</th><th>p min</th><th>p max</th><th>w min</th><th>w max</th>
            <th>t min</th><th>t max</th><th>p min</th><th>p max</th><th>w min</th><th>w max</th>
            <th>t min</th><th>t max</th><th>p min</th><th>p max</th><th>w min</th><th>w max</th>
            <th>t min</th><th>t max</th><th>p min</th><th>p max</th><th>w min</th><th>w max</th>
        </tr></thead><tbody>`;
        filteredData.forEach(row => {{
            let cells = '';
            hours.forEach(h => {{
                const tmin = row[`t${{h}}_min`];
                const tmax = row[`t${{h}}_max`];
                const pmin = row[`p${{h}}_min`];
                const pmax = row[`p${{h}}_max`];
                const wmin = row[`w${{h}}_min`];
                const wmax = row[`w${{h}}_max`];
                cells += `<td style="${{getTempColor(tmin)}}">${{tmin ?? ''}}</td>
                          <td style="${{getTempColor(tmax)}}">${{tmax ?? ''}}</td>
                          <td style="${{getPrecipColor(pmin)}}">${{pmin ?? ''}}</td>
                          <td style="${{getPrecipColor(pmax)}}">${{pmax ?? ''}}</td>
                          <td style="${{getWindColor(wmin)}}">${{wmin ?? ''}}</td>
                          <td style="${{getWindColor(wmax)}}">${{wmax ?? ''}}</td>`;
            }});
            html += `<tr><td>${{row['date']}}</td><td>${{row['name']}}</td><td>${{row['type']}}</td><td>${{row['height'] ?? ''}}</td>${{cells}}</tr>`;
        }});
        html += `</tbody></table>`;
        document.getElementById('tableContainer').innerHTML = html;
    }}

    function updatePointOptions() {{
        const selectedDate = document.getElementById('dateSelect').value;
        const selectedType = document.getElementById('typeFilter').value;
        let filtered = data;
        if (selectedDate) filtered = filtered.filter(r => r['date'] === selectedDate);
        if (selectedType !== 'all') filtered = filtered.filter(r => r['type'] === selectedType);
        const pointNames = [...new Set(filtered.map(r => r['name']))];
        const pointSelect = document.getElementById('pointSelect');
        const currentVal = pointSelect.value;
        pointSelect.innerHTML = '<option value="">-- все точки --</option>';
        pointNames.forEach(p => {{
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            pointSelect.appendChild(opt);
        }});
        if (pointNames.includes(currentVal)) pointSelect.value = currentVal;
        else pointSelect.value = '';
        applyFilters();
    }}

    function updateCharts(pointName) {{
        if (!pointName) {{
            Plotly.react('tempChart', [], {{title: 'Выберите точку'}});
            Plotly.react('precipWindChart', [], {{title: 'Выберите точку'}});
            return;
        }}
        const row = data.find(r => r['name'] === pointName);
        if (!row) return;
        const h = hours;
        const t2024 = h.map(hh => row[`t${{hh}}_2024`]);
        const t2025 = h.map(hh => row[`t${{hh}}_2025`]);
        const tmin = h.map(hh => row[`t${{hh}}_min`]);
        const tmax = h.map(hh => row[`t${{hh}}_max`]);
        Plotly.react('tempChart', [
            {{x: h, y: t2024, name: '2024', type: 'scatter', mode: 'lines+markers', line: {{color: 'blue'}}}},
            {{x: h, y: t2025, name: '2025', type: 'scatter', mode: 'lines+markers', line: {{color: 'red'}}}},
            {{x: h, y: tmin, name: 'min', type: 'scatter', mode: 'lines+markers', line: {{color: 'green', dash: 'dot'}}}},
            {{x: h, y: tmax, name: 'max', type: 'scatter', mode: 'lines+markers', line: {{color: 'orange', dash: 'dot'}}}}
        ], {{title: `Температура — ${{pointName}}`, xaxis: {{title: 'Час', tickvals: h}}, yaxis: {{title: '°C'}}}});
        const p2024 = h.map(hh => row[`p${{hh}}_2024`] || 0);
        const p2025 = h.map(hh => row[`p${{hh}}_2025`] || 0);
        const w2024 = h.map(hh => row[`w${{hh}}_2024`] || 0);
        const w2025 = h.map(hh => row[`w${{hh}}_2025`] || 0);
        Plotly.react('precipWindChart', [
            {{x: h, y: p2024, name: 'Осадки 2024', type: 'bar', marker: {{color: 'lightblue'}}}},
            {{x: h, y: p2025, name: 'Осадки 2025', type: 'bar', marker: {{color: 'lightgreen'}}}},
            {{x: h, y: w2024, name: 'Ветер 2024', type: 'scatter', mode: 'lines+markers', yaxis: 'y2', line: {{color: 'purple'}}}},
            {{x: h, y: w2025, name: 'Ветер 2025', type: 'scatter', mode: 'lines+markers', yaxis: 'y2', line: {{color: 'brown'}}}}
        ], {{title: `Осадки и ветер — ${{pointName}}`, xaxis: {{title: 'Час', tickvals: h}}, yaxis: {{title: 'Осадки (мм)'}}, yaxis2: {{title: 'Ветер (м/с)', overlaying: 'y', side: 'right'}}}});
    }}

    function applyFilters() {{
        const selectedDate = document.getElementById('dateSelect').value;
        const selectedType = document.getElementById('typeFilter').value;
        const selectedPoint = document.getElementById('pointSelect').value;
        let filtered = data;
        if (selectedDate) filtered = filtered.filter(r => r['date'] === selectedDate);
        if (selectedType !== 'all') filtered = filtered.filter(r => r['type'] === selectedType);
        if (selectedPoint) filtered = filtered.filter(r => r['name'] === selectedPoint);
        renderTable(filtered);
        if (selectedPoint) updateCharts(selectedPoint);
        else if (filtered.length > 0) updateCharts(filtered[0]['name']);
        else updateCharts(null);
    }}

    function resetFilters() {{
        document.getElementById('dateSelect').value = '';
        document.getElementById('typeFilter').value = 'all';
        document.getElementById('pointSelect').value = '';
        updatePointOptions();
    }}

    window.onload = function() {{
        updatePointOptions();
        document.getElementById('dateSelect').onchange = updatePointOptions;
        document.getElementById('typeFilter').onchange = updatePointOptions;
        document.getElementById('pointSelect').onchange = applyFilters;
    }};
</script>
</body>
</html>
    """
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ Дашборд сохранён: {output_html}")

# ============================================================
#  ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ---- Обработка GPX с точками погоды ----
    weather_csv_path = None
    if 'WEATHER_POINTS_GPX' in globals() and WEATHER_POINTS_GPX and os.path.exists(WEATHER_POINTS_GPX):
        print("Обработка дополнительного файла с точками погоды:", WEATHER_POINTS_GPX)
        weather_csv_path = process_weather_points(WEATHER_POINTS_GPX, OUTPUT_DIR)
    else:
        if 'WEATHER_POINTS_CSV' in globals() and WEATHER_POINTS_CSV and os.path.exists(WEATHER_POINTS_CSV):
            weather_csv_path = WEATHER_POINTS_CSV

    # ---- Шаг 1: Таблица точек ----
    if 'EXISTING_CSV' in globals() and os.path.exists(EXISTING_CSV):
        print("Использую готовый CSV:", EXISTING_CSV)
        df = pd.read_csv(EXISTING_CSV, encoding='utf-8-sig', sep=';')

        # Страховка: колонка 'type' должна быть
        if 'type' not in df.columns:
            df['type'] = 'точка'
            print("Колонка 'type' отсутствовала — добавлена со значением 'точка'.")

        # Страховка: колонка 'height'
        if 'height' not in df.columns:
            df['height'] = None

        # Дозапрашиваем недостающие высоты
        missing_height = df['height'].isna()
        if missing_height.any():
            print(f"Обнаружено {missing_height.sum()} точек без высоты. Запрашиваю...")
            for idx, row in df[missing_height].iterrows():
                if not pd.isna(row['lat']) and not pd.isna(row['lon']):
                    elev = get_elevation(row['lat'], row['lon'])
                    if elev is not None:
                        df.at[idx, 'height'] = round(elev, 1)
                        print(f"Высота для {row['name']}: {df.at[idx, 'height']} м")
                    time.sleep(0.3)
    else:
        print("Сбор точек маршрута из файлов...")
        plan_path = os.path.join(INPUT_DIR, PLAN_FILE)
        camps_path = os.path.join(INPUT_DIR, CAMPS_FILE)
        villages_path = os.path.join(INPUT_DIR, VILLAGES_FILE)
        passes_path = os.path.join(INPUT_DIR, PASSES_FILE)
        df = build_point_table(plan_path, camps_path, villages_path, passes_path)
        if df.empty:
            print("Не найдено ни одной точки. Проверьте файлы.")
            return
        csv_raw = os.path.join(OUTPUT_DIR, 'points_raw.csv')
        df.to_csv(csv_raw, index=False, encoding='utf-8-sig', sep=';')
        print(f"Собрано {len(df)} точек. Сохранено в {csv_raw}")

    # ---- Шаг 1.5: Объединить с дополнительными точками ----
    if weather_csv_path and os.path.exists(weather_csv_path):
        df = merge_weather_points(df, weather_csv_path, DEFAULT_TYPE, AUTO_DATE_FROM_LAST)

    # ---- Шаг 1.6: Очистка и дедупликация ----
    print("Выполняю очистку данных и дедупликацию...")
    df_clean = clean_and_deduplicate(df, round_digits=DEDUP_ROUND_DIGITS)

    cleaned_csv_path = os.path.join(OUTPUT_DIR, 'points_cleaned.csv')
    df_clean.to_csv(cleaned_csv_path, index=False, encoding='utf-8-sig', sep=';')
    print(f"✅ Очищенный CSV сохранён: {cleaned_csv_path}")

    if 'EXISTING_CSV' in globals() and EXISTING_CSV:
        df_clean.to_csv(EXISTING_CSV, index=False, encoding='utf-8-sig', sep=';')
        print(f"Базовый CSV обновлён (очищенный): {EXISTING_CSV}")

    # ---- Шаг 2: Запрос погоды ----
    print("Запрос исторической погоды...")
    df_final = fetch_weather_for_df(df_clean, YEARS, HOURS)

    # ---- Сортировка по дате ----
    if 'date' in df_final.columns:
        df_final['_date_dt'] = pd.to_datetime(df_final['date'], format='%d.%m.%Y', errors='coerce')
        df_final = df_final.sort_values(by='_date_dt', na_position='last')
        df_final = df_final.drop(columns=['_date_dt'])
        print("✅ Данные отсортированы по дате.")

    csv_full = os.path.join(OUTPUT_DIR, 'points_full.csv')
    df_final.to_csv(csv_full, index=False, encoding='utf-8-sig', sep=';')
    print(f"Полный CSV сохранён: {csv_full}")

    # ---- Шаг 3: Дашборд ----
    html_file = os.path.join(OUTPUT_DIR, 'dashboard.html')
    generate_dashboard_from_df(df_final, html_file, output_csv=None)

    print("\n✅ Всё готово!")
    print(f"  - Очищенный CSV: {cleaned_csv_path}")
    print(f"  - Полный CSV с погодой: {csv_full}")
    print(f"  - Дашборд: {html_file}")

if __name__ == "__main__":
    main()
