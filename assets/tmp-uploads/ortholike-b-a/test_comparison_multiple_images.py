"""
Тестовый скрипт для сравнительного анализа снимков "до/после"
Гипотеза 1: Отправка множественных изображений в одном запросе к LLM

Цель: Проверить, может ли LLM качественно оценить улучшение положения
верхних 4-ок при сравнении боковых снимков до и после лечения.
"""
import os
import sys
import base64
import json
import requests
from PIL import Image
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

# Промпт для сравнительного анализа положения верхних 4-ок
PROMPT_COMPARISON_SYSTEM = """Think in English. Translate the final answer to Russian. Reply in Russian only.

Role: You are an expert orthodontist analyzing treatment progress.

Task: Compare TWO lateral intraoral photographs (before and after treatment) to assess improvement in the position of the upper premolars (upper 4s).

Clinical Context:
- In ideal Class I occlusion (by Angle), the upper 4th tooth (first premolar) should align between the lower 4th and 5th teeth when teeth are in occlusion.
- During orthodontic treatment, we expect the upper 4s to move anteriorly (forward) toward this ideal position.
- The criterion for success: upper 4s improved their position by approximately 3mm (moving toward Class I occlusion).

Analysis Instructions:

1. IMAGE IDENTIFICATION:
   - First image: BEFORE treatment (baseline)
   - Second image: AFTER treatment (at 14 months or later)

2. VISUAL ASSESSMENT:
   - Locate the upper first premolar (upper 4) on both images
   - Locate the lower first premolar (lower 4) and second premolar (lower 5)
   - Observe the relationship between upper 4 and lower teeth in occlusion

3. COMPARISON CRITERIA:
   - Has the upper 4 moved forward (anteriorly)?
   - Is the upper 4 now closer to positioning between lower 4 and lower 5?
   - Is there movement toward Class I occlusion?

4. QUALITATIVE EVALUATION:
   You MUST provide:
   - Overall assessment: "Улучшилось" (Improved) / "Ухудшилось" (Worsened) / "Без изменений" (No change)
   - Confidence level: High / Medium / Low
   - Visual evidence: What specific changes do you observe?
   - Angle Class assessment: Movement toward Class I? Already Class I? Still Class II?
   - Approximate magnitude: Significant improvement / Moderate improvement / Minimal improvement / No improvement

5. OUTPUT FORMAT:
You MUST respond with a structured text in Russian with the following sections:

**ОБЩАЯ ОЦЕНКА:** [Улучшилось/Ухудшилось/Без изменений]

**УВЕРЕННОСТЬ:** [High/Medium/Low]

**ВИЗУАЛЬНЫЕ ПРИЗНАКИ ИЗМЕНЕНИЯ:**
[Детальное описание того, что вы наблюдаете на снимках]

**ОЦЕНКА КЛАССА ПО ЭНГЛЮ:**
[Описание движения к классу I, текущий класс смыкания]

**ВЕЛИЧИНА ИЗМЕНЕНИЯ:**
[Значительное улучшение / Умеренное улучшение / Минимальное улучшение / Без улучшения]

**ДОПОЛНИТЕЛЬНЫЕ НАБЛЮДЕНИЯ:**
[Любые другие заметные изменения: наличие аппаратов, положение других зубов и т.д.]

IMPORTANT: Focus on the RELATIONSHIP between upper 4 and lower teeth, not absolute position in isolation.
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


def preprocess_image_bytes(image_data: bytes) -> str:
    """
    Предобрабатывает изображение точно так же, как в ai_classifier.py
    
    Args:
        image_data: изображение в bytes
        
    Returns:
        str: изображение в base64 формате
    """
    print(f"  ✓ Изображение загружено, размер: {len(image_data)} байт")
    
    # Открываем изображение
    buffer = BytesIO(image_data)
    image = Image.open(buffer)
    
    # Преобразуем в RGB если нужно
    if image.mode in ('RGBA', 'LA'):
        image = image.convert('RGB')
        print(f"  ✓ Конвертировано в RGB")
    
    print(f"  ✓ Размер изображения: {image.size}")
    
    # Проверяем размер (как в ai_classifier.py)
    max_size = 2048
    needs_resize = max(image.size) > max_size
    
    # Создаем новый буфер для JPEG
    output = BytesIO()
    
    # Изменяем размер если нужно
    if needs_resize:
        original_size = image.size
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        print(f"  ✓ Изображение уменьшено: {original_size} → {image.size}")
    
    # Сохраняем как JPEG с высоким качеством (quality=95, как в ai_classifier.py)
    image.save(output, format='JPEG', quality=95)
    
    # Конвертируем в base64
    output.seek(0)
    base64_image = base64.b64encode(output.read()).decode('utf-8')
    
    print(f"  ✓ Изображение подготовлено, base64 длина: {len(base64_image)}")
    
    return base64_image


def compare_images_multiple(base64_image_before: str, base64_image_after: str) -> dict:
    """
    Сравнивает два изображения, отправляя их в одном запросе к LLM
    
    Args:
        base64_image_before: изображение "до" в base64 формате
        base64_image_after: изображение "после" в base64 формате
        
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
    print(f"📝 Метод: Множественные изображения в одном запросе")
    
    # User message с ДВУМЯ изображениями
    user_text = "Проанализируй эти два боковых стоматологических снимка (до и после лечения) и оцени улучшение положения верхних 4-ок согласно инструкции."
    
    # Формируем payload с ДВУМЯ image_url сегментами
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": PROMPT_COMPARISON_SYSTEM
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
                            "url": f"data:image/jpeg;base64,{base64_image_before}"
                        }
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image_after}"
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
    print(f"\n📊 Количество изображений: 2 (before + after)")
    print(f"   - Image 1 (before): {len(base64_image_before)} символов base64")
    print(f"   - Image 2 (after): {len(base64_image_after)} символов base64")
    
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
            "method": "multiple_images",
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
    print("ТЕСТ ГИПОТЕЗЫ 1: МНОЖЕСТВЕННЫЕ ИЗОБРАЖЕНИЯ В ОДНОМ ЗАПРОСЕ")
    print("Сравнительный анализ положения верхних 4-ок")
    print("=" * 80)
    
    # Проверяем аргументы командной строки
    if len(sys.argv) < 3:
        print("\nИспользование:")
        print("  python test_comparison_multiple_images.py <путь_к_файлу_ДО> <путь_к_файлу_ПОСЛЕ>")
        print("\nПример:")
        print("  python dev/local_tests/test_comparison_multiple_images.py \\")
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
        with open(image_before_path, "rb") as f:
            image_before_data = f.read()
        
        # Предобрабатываем
        base64_image_before = preprocess_image_bytes(image_before_data)
        
        print(f"\n📁 Загрузка изображения ПОСЛЕ: {image_after_path}")
        
        # Проверяем существование файла
        if not os.path.exists(image_after_path):
            raise FileNotFoundError(f"Файл не найден: {image_after_path}")
        
        # Загружаем изображение ПОСЛЕ
        with open(image_after_path, "rb") as f:
            image_after_data = f.read()
        
        # Предобрабатываем
        base64_image_after = preprocess_image_bytes(image_after_data)
        
        # Выполняем сравнительный анализ
        result = compare_images_multiple(base64_image_before, base64_image_after)
        
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
        output_file = os.path.join(os.path.dirname(__file__), "comparison_multiple_images_result.json")
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
