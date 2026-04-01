"""
Тестовый скрипт для сравнительного анализа снимков "до/после"
Гипотеза 3: Создание композитного изображения (side-by-side) и отправка одного снимка

Цель: Проверить, может ли LLM качественно оценить улучшение положения
верхних 4-ок при анализе композитного изображения (два снимка рядом).
"""
import os
import sys
import base64
import json
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Отключаем прокси для локального запуска
if 'HTTP_PROXY' in os.environ:
    del os.environ['HTTP_PROXY']
if 'HTTPS_PROXY' in os.environ:
    del os.environ['HTTPS_PROXY']

# Промпт для композитного изображения
PROMPT_COMPARISON_COMPOSITE = """Think in English. Translate the final answer to Russian. Reply in Russian only.

Role: You are an expert orthodontist analyzing treatment progress.

Task: Analyze ONE composite photograph showing TWO lateral intraoral images side-by-side (before treatment on the LEFT, after treatment on the RIGHT) to assess improvement in the position of the upper premolars (upper 4s).

IMAGE LAYOUT:
- LEFT side: BEFORE treatment (baseline)
- RIGHT side: AFTER treatment (at 14 months or later)
- Images may have text labels "ДО" (before) and "ПОСЛЕ" (after) at the top

Clinical Context:
- In ideal Class I occlusion (by Angle), the upper 4th tooth (first premolar) should align between the lower 4th and 5th teeth when teeth are in occlusion.
- During orthodontic treatment, we expect the upper 4s to move anteriorly (forward) toward this ideal position.
- The criterion for success: upper 4s improved their position by approximately 3mm (moving toward Class I occlusion).

Analysis Instructions:

1. IMAGE IDENTIFICATION:
   - Locate the image on the LEFT (before treatment)
   - Locate the image on the RIGHT (after treatment)

2. VISUAL ASSESSMENT FOR EACH IMAGE:
   - Locate the upper first premolar (upper 4) on both images
   - Locate the lower first premolar (lower 4) and second premolar (lower 5)
   - Observe the relationship between upper 4 and lower teeth in occlusion

3. COMPARISON CRITERIA:
   - Has the upper 4 moved forward (anteriorly) from LEFT to RIGHT image?
   - Is the upper 4 now closer to positioning between lower 4 and lower 5?
   - Is there movement toward Class I occlusion?

4. QUALITATIVE EVALUATION:
   You MUST provide:
   - Overall assessment: "Улучшилось" (Improved) / "Ухудшилось" (Worsened) / "Без изменений" (No change)
   - Confidence level: High / Medium / Low
   - Visual evidence: What specific changes do you observe between LEFT and RIGHT?
   - Angle Class assessment: Movement toward Class I? Already Class I? Still Class II?
   - Approximate magnitude: Significant improvement / Moderate improvement / Minimal improvement / No improvement

5. OUTPUT FORMAT:
You MUST respond with a structured text in Russian with the following sections:

**ОБЩАЯ ОЦЕНКА:** [Улучшилось/Ухудшилось/Без изменений]

**УВЕРЕННОСТЬ:** [High/Medium/Low]

**ВИЗУАЛЬНЫЕ ПРИЗНАКИ ИЗМЕНЕНИЯ:**
[Детальное описание того, что вы наблюдаете на снимках СЛЕВА (до) и СПРАВА (после)]

**ОЦЕНКА КЛАССА ПО ЭНГЛЮ:**
[Описание движения к классу I, текущий класс смыкания]

**ВЕЛИЧИНА ИЗМЕНЕНИЯ:**
[Значительное улучшение / Умеренное улучшение / Минимальное улучшение / Без улучшения]

**ДОПОЛНИТЕЛЬНЫЕ НАБЛЮДЕНИЯ:**
[Любые другие заметные изменения: наличие аппаратов, положение других зубов и т.д.]

IMPORTANT: 
- Focus on comparing LEFT (before) vs RIGHT (after)
- Focus on the RELATIONSHIP between upper 4 and lower teeth, not absolute position in isolation
"""

# Получаем настройки из переменных окружения
class SimpleSettings:
    """Упрощенные настройки без валидации для тестирования"""
    def __init__(self):
        self.openrouter_api_key = os.getenv('ORTHOLIKE_OPENROUTER_API_KEY')
        self.openrouter_model = os.getenv('OPENROUTER_MODEL', 'google/gemini-2.0-flash-exp:free')
        self.temperature = float(os.getenv('AI_TEMPERATURE', '0.2'))
        self.top_p = float(os.getenv('AI_TOP_P', '0.2'))
        self.top_k = int(os.getenv('AI_TOP_K', '35'))
        self.max_tokens = int(os.getenv('AI_MAX_TOKENS', '2000'))
        self.request_timeout = int(os.getenv('AI_REQUEST_TIMEOUT', '60'))

settings = SimpleSettings()


def create_composite_image(image_before: Image.Image, image_after: Image.Image) -> Image.Image:
    """
    Создает композитное изображение из двух снимков side-by-side
    
    Args:
        image_before: PIL Image объект снимка "до"
        image_after: PIL Image объект снимка "после"
        
    Returns:
        Image: композитное изображение
    """
    print("\n🎨 Создание композитного изображения...")
    
    # Конвертируем в RGB если нужно
    if image_before.mode in ('RGBA', 'LA'):
        image_before = image_before.convert('RGB')
    if image_after.mode in ('RGBA', 'LA'):
        image_after = image_after.convert('RGB')
    
    # Получаем размеры
    w1, h1 = image_before.size
    w2, h2 = image_after.size
    
    print(f"  ✓ Размер изображения ДО: {w1}x{h1}")
    print(f"  ✓ Размер изображения ПОСЛЕ: {w2}x{h2}")
    
    # Определяем общую высоту (максимум из двух)
    max_height = max(h1, h2)
    
    # Масштабируем изображения к одной высоте для лучшего отображения
    if h1 != max_height:
        scale_factor = max_height / h1
        new_w1 = int(w1 * scale_factor)
        image_before = image_before.resize((new_w1, max_height), Image.Resampling.LANCZOS)
        w1 = new_w1
        print(f"  ✓ Масштабировано ДО: {w1}x{max_height}")
    
    if h2 != max_height:
        scale_factor = max_height / h2
        new_w2 = int(w2 * scale_factor)
        image_after = image_after.resize((new_w2, max_height), Image.Resampling.LANCZOS)
        w2 = new_w2
        print(f"  ✓ Масштабировано ПОСЛЕ: {w2}x{max_height}")
    
    # Добавляем пространство сверху для текстовых меток
    text_height = 80
    total_height = max_height + text_height
    
    # Создаем композитное изображение
    composite_width = w1 + w2
    composite = Image.new('RGB', (composite_width, total_height), color='white')
    
    # Вставляем изображения
    composite.paste(image_before, (0, text_height))
    composite.paste(image_after, (w1, text_height))
    
    print(f"  ✓ Композитное изображение создано: {composite_width}x{total_height}")
    
    # Добавляем текстовые метки
    draw = ImageDraw.Draw(composite)
    
    # Пытаемся загрузить системный шрифт, если не получается - используем дефолтный
    try:
        # Попробуем несколько вариантов шрифтов
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Geneva.dfont"
        ]
        font = None
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font = ImageFont.truetype(font_path, 60)
                    break
                except:
                    continue
        if font is None:
            # Если не удалось загрузить ни один шрифт, используем дефолтный
            font = ImageFont.load_default()
            print("  ⚠️  Используется дефолтный шрифт (метки будут мелкими)")
    except Exception as e:
        font = ImageFont.load_default()
        print(f"  ⚠️  Не удалось загрузить TrueType шрифт: {e}")
    
    # Рисуем метки "ДО" и "ПОСЛЕ"
    text_before = "ДО"
    text_after = "ПОСЛЕ"
    
    # Позиции для центрирования текста
    try:
        bbox_before = draw.textbbox((0, 0), text_before, font=font)
        bbox_after = draw.textbbox((0, 0), text_after, font=font)
        text_w_before = bbox_before[2] - bbox_before[0]
        text_w_after = bbox_after[2] - bbox_after[0]
    except:
        # Fallback для старых версий PIL
        text_w_before = len(text_before) * 30
        text_w_after = len(text_after) * 30
    
    pos_before = ((w1 - text_w_before) // 2, 10)
    pos_after = (w1 + (w2 - text_w_after) // 2, 10)
    
    # Рисуем текст с красной и зеленой обводкой для лучшей видимости
    draw.text(pos_before, text_before, fill='red', font=font)
    draw.text(pos_after, text_after, fill='green', font=font)
    
    print("  ✓ Текстовые метки добавлены")
    
    return composite


def preprocess_composite_image(composite: Image.Image) -> str:
    """
    Предобрабатывает композитное изображение для отправки к LLM
    
    Args:
        composite: PIL Image объект композитного изображения
        
    Returns:
        str: изображение в base64 формате
    """
    print("\n📦 Предобработка композитного изображения...")
    
    # Проверяем размер и масштабируем если необходимо
    max_size = 2048
    width, height = composite.size
    
    if max(width, height) > max_size:
        # Масштабируем сохраняя пропорции
        if width > height:
            new_width = max_size
            new_height = int(height * (max_size / width))
        else:
            new_height = max_size
            new_width = int(width * (max_size / height))
        
        print(f"  ✓ Масштабирование: {width}x{height} → {new_width}x{new_height}")
        composite = composite.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Сохраняем в JPEG формат
    output = BytesIO()
    composite.save(output, format='JPEG', quality=95)
    output.seek(0)
    
    # Конвертируем в base64
    base64_image = base64.b64encode(output.read()).decode('utf-8')
    
    print(f"  ✓ Композитное изображение подготовлено, base64 длина: {len(base64_image)}")
    
    return base64_image


def compare_composite_image(base64_composite: str) -> dict:
    """
    Отправляет композитное изображение для анализа
    
    Args:
        base64_composite: композитное изображение в base64 формате
        
    Returns:
        dict: результат сравнительного анализа
    """
    # Получаем настройки
    api_key = os.getenv('ORTHOLIKE_OPENROUTER_API_KEY') or settings.openrouter_api_key
    model = settings.openrouter_model
    
    if not api_key:
        raise ValueError("ORTHOLIKE_OPENROUTER_API_KEY не установлен")
    
    if not model:
        raise ValueError("OPENROUTER_MODEL не установлен")
    
    print(f"\n🤖 Модель: {model}")
    print(f"🔑 API ключ: {api_key[:8]}...{api_key[-4:]}")
    print(f"📝 Метод: Композитное изображение (side-by-side)")
    
    # User message с ОДНИМ композитным изображением
    user_text = "Проанализируй это композитное изображение с двумя боковыми стоматологическими снимками (слева - до, справа - после лечения) и оцени улучшение положения верхних 4-ок согласно инструкции."
    
    # Формируем payload с ОДНИМ image_url
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": PROMPT_COMPARISON_COMPOSITE
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_text
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_composite}"
                        }
                    }
                ]
            }
        ],
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "max_tokens": settings.max_tokens,
    }
    
    # top_k только для не-OpenAI моделей
    if not model.startswith("openai/"):
        payload["top_k"] = settings.top_k
    
    print(f"\n⚙️  Sampling параметры:")
    print(f"   - temperature: {payload['temperature']}")
    print(f"   - top_p: {payload['top_p']}")
    if 'top_k' in payload:
        print(f"   - top_k: {payload['top_k']}")
    print(f"   - max_tokens: {payload['max_tokens']}")
    print(f"\n📊 Композитное изображение: {len(base64_composite)} символов base64")
    
    # Отправляем запрос
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    print("\n📤 Отправка запроса к OpenRouter...")
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=settings.request_timeout
        )
        
        response.raise_for_status()
        result = response.json()
        
        print("✓ Ответ получен")
        
        # Извлекаем текст ответа
        content = result['choices'][0]['message']['content']
        
        return {
            "success": True,
            "method": "composite_image",
            "model": model,
            "response": content,
            "usage": result.get('usage', {}),
            "full_response": result
        }
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Статус: {e.response.status_code}")
            try:
                error_body = e.response.json()
                print(f"   Ошибка: {json.dumps(error_body, indent=2, ensure_ascii=False)}")
            except:
                print(f"   Тело ответа: {e.response.text[:500]}")
        raise


def main():
    """Основная функция"""
    print("=" * 80)
    print("ТЕСТ ГИПОТЕЗЫ 3: КОМПОЗИТНОЕ ИЗОБРАЖЕНИЕ (SIDE-BY-SIDE)")
    print("Сравнительный анализ положения верхних 4-ок")
    print("=" * 80)
    
    # Проверяем аргументы командной строки
    if len(sys.argv) < 3:
        print("\nИспользование:")
        print("  python test_comparison_composite_image.py <путь_к_файлу_ДО> <путь_к_файлу_ПОСЛЕ>")
        print("\nПример:")
        print("  python dev/local_tests/test_comparison_composite_image.py \\")
        print("    dev/local_tests/b:a/before_MG_6302.JPG \\")
        print("    'dev/local_tests/b:a/after_IMG_2795 — копия.JPG'")
        return 1
    
    image_before_path = sys.argv[1]
    image_after_path = sys.argv[2]
    
    try:
        print(f"\n📁 Загрузка изображения ДО: {image_before_path}")
        
        # Проверяем существование файла
        if not os.path.exists(image_before_path):
            raise FileNotFoundError(f"Файл не найден: {image_before_path}")
        
        # Загружаем изображение ДО
        image_before = Image.open(image_before_path)
        print(f"  ✓ Изображение загружено: {image_before.size}")
        
        print(f"\n📁 Загрузка изображения ПОСЛЕ: {image_after_path}")
        
        # Проверяем существование файла
        if not os.path.exists(image_after_path):
            raise FileNotFoundError(f"Файл не найден: {image_after_path}")
        
        # Загружаем изображение ПОСЛЕ
        image_after = Image.open(image_after_path)
        print(f"  ✓ Изображение загружено: {image_after.size}")
        
        # Создаем композитное изображение
        composite = create_composite_image(image_before, image_after)
        
        # Сохраняем композитное изображение для визуальной проверки
        composite_path = os.path.join(os.path.dirname(__file__), "composite_comparison.jpg")
        composite.save(composite_path, quality=95)
        print(f"\n💾 Композитное изображение сохранено: {composite_path}")
        
        # Предобрабатываем для отправки
        base64_composite = preprocess_composite_image(composite)
        
        # Выполняем сравнительный анализ
        result = compare_composite_image(base64_composite)
        
        # Выводим результат
        print("\n" + "=" * 80)
        print("РЕЗУЛЬТАТ СРАВНИТЕЛЬНОГО АНАЛИЗА")
        print("=" * 80)
        print(f"\n{result['response']}")
        print("\n" + "-" * 80)
        
        # Статистика использования
        if 'usage' in result and result['usage']:
            usage = result['usage']
            print(f"\n📊 Использование токенов:")
            print(f"   - prompt: {usage.get('prompt_tokens', 'N/A')}")
            print(f"   - completion: {usage.get('completion_tokens', 'N/A')}")
            print(f"   - total: {usage.get('total_tokens', 'N/A')}")
        
        # Сохраняем полный результат в JSON
        output_file = os.path.join(os.path.dirname(__file__), "comparison_composite_result.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Полный результат сохранен в: {output_file}")
        
        print("\n" + "=" * 80)
        return 0
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
