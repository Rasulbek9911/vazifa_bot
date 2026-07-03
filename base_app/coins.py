from django.db import transaction as db_transaction
from django.utils import timezone


def award_task_coins(student, topic, grade, deadline_passed, task_type='test'):
    """
    Student vazifa bajarganida tanga berish.
    grade: already deadline-adjusted grade value
    Returns dict {result_coins, streak_coins, new_streak, total, total_wallet} yoki None.
    """
    from .models import CoinWallet, CoinTransaction, Topic, Task as TaskModel

    course = topic.course
    if not course or grade is None:
        return None

    with db_transaction.atomic():
        wallet, _ = CoinWallet.objects.select_for_update().get_or_create(
            student=student, course=course
        )

        # Bir mavzu uchun bir marta beriladi
        if CoinTransaction.objects.filter(wallet=wallet, topic=topic, task_type=task_type).exists():
            return None

        result_coins = max(0, grade)

        last_topic_id = wallet.last_topic_id
        last_submitted_at = wallet.last_submitted_at

        if last_topic_id is None:
            new_streak = 1
        else:
            completed_ids = list(TaskModel.objects.filter(
                student=student, topic__course=course
            ).values_list('topic_id', flat=True))

            if topic.activated_at is not None:
                # Shu topicgacha (shu batch bilan birga) topshirilmagan active topic bor = gap bor
                has_gap = Topic.objects.filter(
                    course=course,
                    is_active=True,
                    activated_at__lte=topic.activated_at,
                ).exclude(id__in=completed_ids).exclude(id=topic.id).exists()
            else:
                # activated_at yo'q bo'lsa: id bo'yicha oradagi topiclarni tekshir
                has_gap = Topic.objects.filter(
                    course=course,
                    is_active=True,
                    id__gt=last_topic_id,
                    id__lt=topic.id,
                ).exclude(id__in=completed_ids).exists()

            new_streak = 1 if has_gap else wallet.current_streak + 1

        streak_coins = new_streak
        total = result_coins + streak_coins

        wallet.total_coins += total
        wallet.current_streak = new_streak
        if new_streak > wallet.longest_streak:
            wallet.longest_streak = new_streak
        wallet.last_topic = topic
        wallet.last_submitted_at = timezone.now()
        wallet.save()

        CoinTransaction.objects.create(
            wallet=wallet,
            topic=topic,
            task_type=task_type,
            result_coins=result_coins,
            streak_coins=streak_coins,
            total_coins=total,
            streak_after=new_streak,
            deadline_penalty=deadline_passed,
        )

        return {
            'result_coins': result_coins,
            'streak_coins': streak_coins,
            'new_streak': new_streak,
            'total': total,
            'total_wallet': wallet.total_coins,
            'longest_streak': wallet.longest_streak,
        }
