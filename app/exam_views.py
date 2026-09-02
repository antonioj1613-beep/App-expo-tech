"""
Mock exams — full timed TOEIC-style practice tests. Separate module from
lesson_service.py on purpose: see the MockExam docstring in models.py for
why this doesn't reuse SkillLesson's one-item-at-a-time, completed-once
shape. Unlimited reattempts by design, so there's no "next lesson" walk
here -- every visit to exam_take() starts a brand new MockExamAttempt.
"""

from __future__ import annotations

from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import login_required
from .models import MockExam, MockExamAttempt
from .user_helpers import get_logged_in_user


@login_required
def exams(request):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")

    exam_list = []
    for exam in MockExam.objects.filter(is_published=True).prefetch_related("questions"):
        attempts = MockExamAttempt.objects.filter(exam=exam, submitted_at__isnull=False)
        best = attempts.filter(user=user).order_by("-score_percent").first()
        exam_list.append(
            {
                "exam": exam,
                "question_count": exam.question_count,
                "attempt_count": attempts.count(),
                "your_best_score": best.score_percent if best else None,
            }
        )

    return render(request, "exams.html", {"active": "exams", "exam_list": exam_list})


@login_required
def exam_take(request, slug):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")

    exam = get_object_or_404(MockExam, slug=slug, is_published=True)
    questions = list(exam.questions.all())
    if not questions:
        return redirect("exams")

    attempt = MockExamAttempt.objects.create(user=user, exam=exam, total_questions=len(questions))

    return render(
        request,
        "exam_take.html",
        {
            "active": "exams",
            "exam": exam,
            "questions": questions,
            "attempt_id": attempt.id,
            "time_limit_seconds": exam.time_limit_minutes * 60,
        },
    )


@login_required
@require_POST
def exam_submit(request, attempt_id):
    user = get_logged_in_user(request)
    if not user:
        return JsonResponse({"error": "Not authenticated."}, status=401)

    attempt = get_object_or_404(MockExamAttempt, pk=attempt_id, user=user)
    if attempt.submitted_at is not None:
        return JsonResponse({"error": "This attempt was already submitted."}, status=400)

    questions = list(attempt.exam.questions.all())
    answers: dict[str, int] = {}
    correct_count = 0

    for question in questions:
        raw = request.POST.get(f"answer_{question.id}")
        try:
            selected = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            selected = None
        if selected is not None:
            answers[str(question.id)] = selected
            if selected == question.correct_index:
                correct_count += 1

    total = len(questions) or 1
    attempt.answers = answers
    attempt.correct_count = correct_count
    attempt.score_percent = Decimal(correct_count * 100) / Decimal(total)
    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=["answers", "correct_count", "score_percent", "submitted_at"])

    return JsonResponse({"ok": True, "attempt_id": attempt.id, "results_url": f"/exams/results/{attempt.id}/"})


@login_required
def exam_results(request, attempt_id):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")

    attempt = get_object_or_404(MockExamAttempt, pk=attempt_id, user=user)
    if attempt.submitted_at is None:
        return redirect("exam_take", slug=attempt.exam.slug)

    rows = []
    for question in attempt.exam.questions.all():
        selected = attempt.answers.get(str(question.id))
        rows.append(
            {
                "question": question,
                "selected_index": selected,
                "was_correct": selected == question.correct_index,
                "was_answered": selected is not None,
            }
        )

    return render(
        request,
        "exam_results.html",
        {"active": "exams", "attempt": attempt, "rows": rows},
    )
