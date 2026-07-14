#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import argparse
from datetime import datetime
from collections import defaultdict

DEFAULT_INPUT = "output.csv"
DEFAULT_OUTPUT = "report.html"

# ------------------- БАЗОВЫЕ НАСТРОЙКИ ОТОБРАЖЕНИЯ --------------------
BASE_COLUMNS = [
    "date",                     # 1. Дата
    "name",                     # 2. Название
    "type",                     # 3. Тип точки
    "height",                   # 4. Высота (м)
    "lat",                      # 5. Широта
    "lon",                      # 6. Долгота
    "temperature_max",          # 7. Температура макс (°C)
    "temperature_min",          # 8. Температура мин (°C)
    "precipitation",            # 9. Осадки (мм)
    "precipitation_probability",# 10. Вероятность осадков (%)
    "windspeed_max",            # 11. Ветер макс (м/с)
    "predictability",           # 12. Прогнозируемость (%)
    "pictocode",                # 13. Погода
]

EXCLUDED_FROM_LEGEND = ["name", "type", "date", "height", "lat", "lon"]

PRETTY_HEADERS = {
    "name": "Название",
    "type": "Тип",
    "date": "Дата",
    "height": "Высота (м)",
    "lat": "Широта",
    "lon": "Долгота",
    "totalcloudcover_min": "Облачность мин (%)",
    "totalcloudcover_max": "Облачность макс (%)",
    "totalcloudcover_mean": "Облачность сред (%)",
    "totalcloudcover_spread": "Разброс облачности",
    "precipitation": "Осадки (мм)",
    "precipitation_spread": "Разброс осадков",
    "precipitation_probability": "Вероятность осадков (%)",
    "snowfraction": "Доля снега (%)",
    "temperature_min": "Температура мин (°C)",
    "temperature_max": "Температура макс (°C)",
    "temperature_mean": "Температура сред (°C)",
    "temperature_spread": "Разброс температуры",
    "windspeed_min": "Ветер мин (м/с)",
    "windspeed_max": "Ветер макс (м/с)",
    "windspeed_mean": "Ветер сред (м/с)",
    "windspeed_spread": "Разброс ветра",
    "winddirection": "Направление ветра (°)",
    "sealevelpressure_min": "Давление мин (гПа)",
    "sealevelpressure_max": "Давление макс (гПа)",
    "sealevelpressure_mean": "Давление сред (гПа)",
    "relativehumidity_min": "Влажность мин (%)",
    "relativehumidity_max": "Влажность макс (%)",
    "relativehumidity_mean": "Влажность сред (%)",
    "predictability": "Прогнозируемость (%)",
    "predictability_class": "Класс прогнозируемости",
    "ghi_total": "Солн. радиация (Вт·ч/м²)",
    "extraterrestrialradiation_total": "Внеатм. радиация (Вт·ч/м²)",
    "pictocode": "Погода",
}

PARAM_DESCRIPTIONS = {
    "totalcloudcover_min": "Минимальная суточная облачность. Наименьший процент неба, закрытого облаками, в течение дня.",
    "totalcloudcover_max": "Максимальная суточная облачность. Наибольший процент неба, закрытого облаками, в течение дня.",
    "totalcloudcover_mean": "Средняя суточная облачность. Среднее значение облачности за день.",
    "totalcloudcover_spread": "Разброс облачности. Показывает вариативность (неопределённость) прогноза облачности, основанную на ансамбле моделей. Большое значение означает меньшую уверенность в прогнозе.",
    "precipitation": "Суммарные осадки за день. Общее количество осадков (в мм), выпавших за сутки.",
    "precipitation_spread": "Разброс осадков. Показывает вариативность прогноза осадков между разными моделями (ансамблем).",
    "precipitation_probability": "Вероятность осадков. Вероятность (в процентах) того, что в этот день будут осадки.",
    "snowfraction": "Доля снега. Процент от общего количества осадков, выпавший в виде снега (а не дождя).",
    "temperature_min": "Минимальная суточная температура. Самая низкая температура за день (в °C).",
    "temperature_max": "Максимальная суточная температура. Самая высокая температура за день (в °C).",
    "temperature_mean": "Средняя суточная температура. Среднее значение температуры за день.",
    "temperature_spread": "Разброс температуры. Показывает вариативность прогноза температуры между разными моделями (ансамблем).",
    "windspeed_min": "Минимальная скорость ветра за день (в м/с).",
    "windspeed_max": "Максимальная скорость ветра за день (в м/с).",
    "windspeed_mean": "Средняя скорость ветра за день (в м/с).",
    "windspeed_spread": "Разброс скорости ветра. Показывает вариативность прогноза ветра между разными моделями (ансамблем).",
    "winddirection": "Направление ветра. Направление, откуда дует ветер (в градусах: 0° — север, 90° — восток и т.д.).",
    "sealevelpressure_min": "Минимальное давление на уровне моря за день (в гПа).",
    "sealevelpressure_max": "Максимальное давление на уровне моря за день (в гПа).",
    "sealevelpressure_mean": "Среднее давление на уровне моря за день (в гПа).",
    "relativehumidity_min": "Минимальная относительная влажность за день (в %).",
    "relativehumidity_max": "Максимальная относительная влажность за день (в %).",
    "relativehumidity_mean": "Средняя относительная влажность за день (в %).",
    "predictability": "Прогнозируемость. Оценка уверенности модели в прогнозе (в процентах). Чем выше значение, тем надёжнее прогноз.",
    "predictability_class": "Класс прогнозируемости. Качественная (категориальная) оценка надёжности прогноза (например, 'высокая', 'средняя', 'низкая').",
    "ghi_total": "Суммарная глобальная горизонтальная радиация. Общее количество солнечной энергии, падающей на горизонтальную поверхность за день (в Вт·ч/м²).",
    "extraterrestrialradiation_total": "Суммарная внеатмосферная радиация. Количество солнечной энергии, поступающей на верхнюю границу атмосферы за день (в Вт·ч/м²).",
    "pictocode": "Код пиктограммы. Числовой код, соответствующий определённому значку погоды (солнечно, облачно, дождь и т.д.). Используется для отображения иконки прогноза.",
}

CATEGORIES = {
    "totalcloudcover_min": "Облачность",
    "totalcloudcover_max": "Облачность",
    "totalcloudcover_mean": "Облачность",
    "totalcloudcover_spread": "Облачность",
    "precipitation": "Осадки",
    "precipitation_spread": "Осадки",
    "precipitation_probability": "Осадки",
    "snowfraction": "Осадки",
    "temperature_min": "Температура",
    "temperature_max": "Температура",
    "temperature_mean": "Температура",
    "temperature_spread": "Температура",
    "windspeed_min": "Ветер",
    "windspeed_max": "Ветер",
    "windspeed_mean": "Ветер",
    "windspeed_spread": "Ветер",
    "winddirection": "Ветер",
    "sealevelpressure_min": "Давление",
    "sealevelpressure_max": "Давление",
    "sealevelpressure_mean": "Давление",
    "relativehumidity_min": "Влажность",
    "relativehumidity_max": "Влажность",
    "relativehumidity_mean": "Влажность",
    "predictability": "Прогнозируемость",
    "predictability_class": "Прогнозируемость",
    "ghi_total": "Солнечная радиация",
    "extraterrestrialradiation_total": "Солнечная радиация",
    "pictocode": "Пиктограмма",
}

CATEGORY_ORDER = [
    "Облачность",
    "Осадки",
    "Температура",
    "Ветер",
    "Давление",
    "Влажность",
    "Прогнозируемость",
    "Солнечная радиация",
    "Пиктограмма",
]

def pictocode_to_symbol(code):
    try:
        code = int(code)
    except (ValueError, TypeError):
        return "❓"
    if code <= 2:
        return "☀️"
    elif code <= 4:
        return "🌤️"
    elif code <= 6:
        return "⛅"
    elif code <= 8:
        return "☁️"
    elif code <= 10:
        return "🌧️"
    elif code <= 12:
        return "⛈️"
    elif code <= 14:
        return "🌨️"
    elif code <= 16:
        return "🌫️"
    else:
        return "🌈"

def generate_html_report(csv_file, html_file, extra_columns=None, show_all=False):
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        all_fieldnames = reader.fieldnames
        rows = list(reader)

    if not rows:
        print("⚠️  Нет данных для отчёта.")
        return

    if show_all:
        table_cols = all_fieldnames[:]
    else:
        table_cols = []
        for col in BASE_COLUMNS:
            if col in all_fieldnames:
                table_cols.append(col)
        if extra_columns:
            for col in extra_columns:
                if col in all_fieldnames and col not in table_cols:
                    table_cols.append(col)

    legend_params = [col for col in all_fieldnames if col not in EXCLUDED_FROM_LEGEND and col in PARAM_DESCRIPTIONS]

    html = []
    html.append("<!DOCTYPE html>")
    html.append("<html lang='ru'>")
    html.append("<head>")
    html.append("<meta charset='UTF-8'>")
    html.append("<meta name='viewport' content='width=device-width, initial-scale=1.0'>")
    html.append("<title>Прогноз погоды – meteoblue</title>")
    html.append("<style>")
    html.append("""
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 20px;
            background: #f0f4f8;
            color: #2c3e50;
        }
        h1 {
            font-size: 28px;
            margin-bottom: 5px;
            color: #1a2b3c;
        }
        .subtitle {
            font-size: 16px;
            color: #5a6b7c;
            margin-top: 0;
            margin-bottom: 25px;
        }
        .table-wrapper {
            overflow-x: auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            padding: 5px 0;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            font-size: 14px;
            min-width: 600px;
        }
        th, td {
            padding: 10px 12px;
            border: 1px solid #dde4ec;
            text-align: center;
            white-space: nowrap;
        }
        th {
            background: #2c3e50;
            color: white;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        tr:nth-child(even) {
            background: #f8fafc;
        }
        tr:hover {
            background: #e9eff5;
        }
        .legend {
            margin-top: 30px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            padding: 20px 25px;
        }
        .legend h2 {
            font-size: 20px;
            margin-top: 0;
            color: #1a2b3c;
            border-bottom: 2px solid #e9eff5;
            padding-bottom: 10px;
        }
        .legend-category {
            font-size: 18px;
            font-weight: 600;
            color: #1a2b3c;
            margin-top: 18px;
            margin-bottom: 8px;
            border-left: 4px solid #2980b9;
            padding-left: 10px;
        }
        .legend-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 6px 20px;
            margin-bottom: 12px;
        }
        .legend-item {
            display: flex;
            align-items: baseline;
            font-size: 14px;
        }
        .legend-item strong {
            min-width: 160px;
            font-weight: 600;
            color: #2c3e50;
        }
        .legend-item span {
            color: #5a6b7c;
        }
        .footer {
            margin-top: 20px;
            font-size: 13px;
            color: #7f8c8d;
            border-top: 1px solid #dde4ec;
            padding-top: 15px;
        }
        .footer a {
            color: #2980b9;
            text-decoration: none;
        }
        .footer a:hover {
            text-decoration: underline;
        }
        .picto-symbol {
            font-size: 22px;
        }
    """)
    html.append("</style>")
    html.append("</head>")
    html.append("<body>")
    html.append(f"<h1>📊 Прогноз погоды</h1>")
    html.append(f"<div class='subtitle'>Пакет trend-day • 14 дней • от {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>")

    html.append("<div class='table-wrapper'>")
    html.append("<table>")
    html.append("<thead><tr>")
    for col in table_cols:
        display = PRETTY_HEADERS.get(col, col)
        html.append(f"<th>{display}</th>")
    html.append("</tr></thead>")

    html.append("<tbody>")
    for row in rows:
        html.append("<tr>")
        for col in table_cols:
            value = row.get(col, "")
            if col == "pictocode" and value:
                symbol = pictocode_to_symbol(value)
                html.append(f"<td class='picto-symbol'>{symbol}</td>")
                continue
            if value and col not in ["name", "type", "date", "height", "lat", "lon", "predictability_class"]:
                try:
                    val = float(value)
                    if val.is_integer():
                        value = str(int(val))
                    else:
                        value = f"{val:.1f}"
                except (ValueError, TypeError):
                    pass
            html.append(f"<td>{value}</td>")
        html.append("</tr>")
    html.append("</tbody>")
    html.append("</table>")
    html.append("</div>")

    html.append("<div class='legend'>")
    html.append("<h2>📖 Полное описание всех параметров</h2>")

    groups = defaultdict(list)
    for param in legend_params:
        cat = CATEGORIES.get(param, "Прочее")
        pretty = PRETTY_HEADERS.get(param, param)
        desc = PARAM_DESCRIPTIONS.get(param, "Нет описания")
        groups[cat].append((pretty, desc))

    for cat in CATEGORY_ORDER:
        if cat not in groups or not groups[cat]:
            continue
        html.append(f"<div class='legend-category'>{cat}</div>")
        html.append("<div class='legend-grid'>")
        for pretty, desc in groups[cat]:
            html.append(f"<div class='legend-item'><strong>{pretty}:</strong> <span>{desc}</span></div>")
        html.append("</div>")

    html.append("</div>")

    html.append("<div class='footer'>")
    html.append("Источник: <a href='https://www.meteoblue.com' target='_blank'>meteoblue.com</a> • ")
    html.append("Данные получены через API (trend-day)")
    html.append("</div>")

    html.append("</body>")
    html.append("</html>")

    with open(html_file, "w", encoding="utf-8") as f:
        f.write("\n".join(html))
    print(f"🌐 HTML-отчёт сохранён в {html_file}")

def main():
    parser = argparse.ArgumentParser(
        description="Генерация HTML-отчёта из CSV (output.csv) без запросов к API."
    )
    parser.add_argument(
        "--input", "-i",
        default=DEFAULT_INPUT,
        help=f"Путь к входному CSV (по умолчанию {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help=f"Путь к выходному HTML (по умолчанию {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--extra-columns", "-e",
        default="",
        help="Дополнительные колонки для отображения (через запятую), например: temperature_mean,windspeed_mean"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Показать все доступные колонки (включая координаты и высоту)"
    )
    args = parser.parse_args()

    extra_cols = [col.strip() for col in args.extra_columns.split(",") if col.strip()] if args.extra_columns else None
    generate_html_report(args.input, args.output, extra_columns=extra_cols, show_all=args.all)

if __name__ == "__main__":
    main()