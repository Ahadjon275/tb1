```python
import matplotlib.pyplot as plt
import io
from typing import List, Tuple, Dict, Optional

def get_model_usage_for_days(start_timestamp, end_timestamp) -> List[Tuple[str, Dict[str, int]]]:
    usage_data = []
    model_usage = {}

    with my_db.LOCK:
        try:
            # Запрос использования моделей
            my_db.CUR.execute('''
                SELECT model_used, COUNT(*) FROM msg_counter
                WHERE access_time >= ? AND access_time < ?
                GROUP BY model_used
            ''', (start_timestamp, end_timestamp))
            results = my_db.CUR.fetchall()

            for row in results:
                model = row[0]
                usage_count = row[1]
                model_usage[model] = usage_count

            usage_data.append((date_str, model_usage))

        except Exception as error:
            my_log.log2(f'my_db:get_model_usage_for_days {error}')
            return []

    return usage_data


def visualize_usage(usage_data: List[Tuple[str, Dict[str, int]]], mode: str = 'llm') -> Optional[bytes]:
    """
    Визуализирует данные использования моделей во времени.

    Args:
        usage_data: Список кортежей, где каждый кортеж содержит:
            - Дата (YYYY-MM-DD) как строка.
            - Словарь с подсчетом использования моделей за эту дату,
              где ключи - имена моделей (str), а значения - подсчеты (int).
        mode: Режим визуализации ('llm' или 'img'). Если 'llm', отображаются только не изображенческие модели. Если 'img', только изображенческие модели.

    Returns:
        Строка байтов, содержащая данные изображения PNG сгенерированного графика,
        или None, если входные данные пусты.
    """

    if not usage_data:
        my_log.log2('my_db:visualize_usage: Нет данных для визуализации.')
        return None

    dates = [data[0] for data in usage_data]  # Извлечение дат
    models = sorted(set(model for _, usage in usage_data for model in usage))  # Уникальные имена моделей
    model_counts = {model: [] for model in models}  # Инициализация списков счетчиков для каждой модели

    # Заполнение списков данных
    for _, usage in usage_data:
        for model in models:
            model_counts[model].append(usage.get(model, 0))  # Получение подсчета или 0

    fig, ax = plt.subplots(figsize=(10, 6))  # Создание фигуры и оси

    handles_labels_values = []  # Инициализация списка для хранения ручек, меток и значений

    # Построение графика использования моделей
    for model in models:
        if (mode == 'llm' and model.startswith('img ')) or (mode == 'img' and not model.startswith('img ')):
            continue

        label = model[4:] if model.startswith('img ') else model
        line, = ax.plot(dates, model_counts[model], label=label, marker='o')
        
        # Проверка последнего значения для добавления в легенду
        value = model_counts[model][-1]
        if value > 0:
            handles_labels_values.append((line, label, value))

    # Сортировка по значениям в порядке убывания
    handles_labels_values.sort(key=lambda x: x[2], reverse=True)

    # Распаковка кортежей в отдельные списки
    handles, labels, values = zip(*handles_labels_values)

    total_last_day = sum(values)  # Подсчет общего количества за последний день

    ax.set_xlabel("Дата")
    ax.set_ylabel("Количество использования")
    ax.set_title(f"Использование моделей во времени (Всего за последний день: {total_last_day})")
    ax.grid(axis='y', linestyle='--')
    ax.tick_params(axis='x', rotation=45, labelsize=8)

    # Настройка меток по оси X, если дат слишком много
    if len(dates) > 10:
        step = max(1, len(dates) // 10)  # Обеспечение минимального шага
        ax.set_xticks(dates[::step])

    # Добавление легенды
    ax.legend()

    # Сохранение графика в буфер
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)
    
    return buf.getvalue()
