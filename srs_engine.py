"""
Motor de Repetición Espaciada (SRS) basado en el algoritmo de Anki.
Intervalos de aprendizaje especificados:
- Paso 0: 1 minuto (60 s)
- Paso 1: 10 minutos (600 s)
- Paso 2: 1 día (86.400 s) [Graduación -> is_learned = 1]
- Paso 3: 4 días (345.600 s)
- Pasos posteriores: intervalo * ease_factor
"""

from datetime import datetime, timedelta, timezone

# Constantes de tiempo en segundos
SEC_1_MIN = 60
SEC_10_MIN = 600
SEC_1_DAY = 86_400
SEC_4_DAYS = 345_600

DEFAULT_EASE = 2.5
MIN_EASE = 1.3

def format_interval(seconds: int) -> str:
    """Convierte segundos en una etiqueta amigable y legible estilo Anki."""
    if seconds < 60:
        return f"{seconds} s"
    elif seconds < 3600:
        mins = round(seconds / 60)
        return f"{mins} min"
    elif seconds < 86400:
        hrs = round(seconds / 3600)
        return f"{hrs} h"
    elif seconds < 2592000:
        days = round(seconds / 86400)
        return f"{days} día" if days == 1 else f"{days} días"
    else:
        months = round(seconds / 2592000)
        return f"{months} m"

def get_button_intervals(step: int, interval_seconds: int, ease_factor: float, is_learned: int) -> dict:
    """
    Retorna los intervalos en segundos y texto legible para los 4 botones:
    - again (Otra vez): 1 min
    - hard (Difícil): 10 min
    - good (Bien): 1 día (o progresión posterior)
    - easy (Fácil): 4 días (o progresión posterior)
    """
    # 1. Otra vez: Siempre resetea a 1 minuto
    again_sec = SEC_1_MIN

    # 2. Difícil
    if step <= 1:
        hard_sec = SEC_10_MIN
    elif step == 2:
        hard_sec = SEC_1_DAY
    elif step == 3:
        hard_sec = SEC_4_DAYS
    else:
        hard_sec = max(SEC_4_DAYS, int(interval_seconds * 1.2))

    # 3. Bien
    if step <= 1:
        good_sec = SEC_1_DAY
    elif step == 2:
        good_sec = SEC_4_DAYS
    else:
        good_sec = int(interval_seconds * ease_factor)

    # 4. Fácil
    if step <= 1:
        easy_sec = SEC_4_DAYS
    elif step == 2:
        easy_sec = int(SEC_4_DAYS * ease_factor)
    else:
        easy_sec = int(interval_seconds * ease_factor * 1.3)

    return {
        "again": {"seconds": again_sec, "label": format_interval(again_sec)},
        "hard": {"seconds": hard_sec, "label": format_interval(hard_sec)},
        "good": {"seconds": good_sec, "label": format_interval(good_sec)},
        "easy": {"seconds": easy_sec, "label": format_interval(easy_sec)}
    }

def process_review(
    rating: str,
    current_step: int,
    current_interval: int,
    current_ease: float,
    current_repetitions: int,
    current_lapses: int,
    current_is_learned: int
) -> dict:
    """
    Calcula el siguiente estado, intervalo, ease_factor y fecha due_at
    de acuerdo a la calificación recibida ('again', 'hard', 'good', 'easy').
    """
    rating = rating.lower()
    now = datetime.now(timezone.utc)

    new_step = current_step
    new_interval = current_interval
    new_ease = current_ease
    new_repetitions = current_repetitions + 1
    new_lapses = current_lapses
    new_is_learned = current_is_learned
    new_state = 'learning'

    if rating == 'again':
        # Reseteo al paso inicial de 1 minuto
        new_step = 0
        new_interval = SEC_1_MIN
        new_lapses += 1
        new_state = 'learning'
        # Si ya estaba graduado, penaliza ligeramente la facilidad
        if current_is_learned:
            new_ease = max(MIN_EASE, current_ease - 0.20)

    elif rating == 'hard':
        if current_step <= 1:
            new_step = 1
            new_interval = SEC_10_MIN  # 10 min
            new_state = 'learning'
        elif current_step == 2:
            new_step = 2
            new_interval = SEC_1_DAY   # 1 día
            new_state = 'graduated'
            new_ease = max(MIN_EASE, current_ease - 0.15)
        elif current_step == 3:
            new_step = 3
            new_interval = SEC_4_DAYS  # 4 días
            new_state = 'graduated'
            new_ease = max(MIN_EASE, current_ease - 0.15)
        else:
            new_interval = max(SEC_4_DAYS, int(current_interval * 1.2))
            new_ease = max(MIN_EASE, current_ease - 0.15)
            new_state = 'graduated'

    elif rating == 'good':
        if current_step <= 1:
            # 1 día (Graduado / Dominado)
            new_step = 2
            new_interval = SEC_1_DAY
            new_state = 'graduated'
            new_is_learned = 1
        elif current_step == 2:
            # 1 día -> 4 días
            new_step = 3
            new_interval = SEC_4_DAYS
            new_state = 'graduated'
            new_is_learned = 1
        else:
            # Paso > 3: Multiplicar por ease_factor
            new_step = current_step + 1
            new_interval = int(current_interval * current_ease)
            new_state = 'graduated'
            new_is_learned = 1

    elif rating == 'easy':
        # Salto acelerado con bonificación de facilidad
        new_ease = current_ease + 0.15
        if current_step <= 1:
            # Salta directo a 4 días
            new_step = 3
            new_interval = SEC_4_DAYS
            new_state = 'graduated'
            new_is_learned = 1
        elif current_step == 2:
            new_step = 3
            new_interval = int(SEC_4_DAYS * new_ease)
            new_state = 'graduated'
            new_is_learned = 1
        else:
            new_step = current_step + 1
            new_interval = int(current_interval * new_ease * 1.3)
            new_state = 'graduated'
            new_is_learned = 1
    else:
        raise ValueError(f"Calificación desconocida: {rating}. Debe ser again, hard, good o easy.")

    due_at = (now + timedelta(seconds=new_interval)).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "step": new_step,
        "interval_seconds": new_interval,
        "ease_factor": round(new_ease, 2),
        "repetitions": new_repetitions,
        "lapses": new_lapses,
        "state": new_state,
        "is_learned": new_is_learned,
        "due_at": due_at,
        "interval_label": format_interval(new_interval)
    }
