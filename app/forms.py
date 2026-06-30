"""Staff forms for the lesson builder."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from .models import STAFF_SKILL_SLUGS, Skill, SkillLesson


class SkillLessonStaffForm(forms.ModelForm):
    option_1 = forms.CharField(label="Option A", required=False, widget=forms.TextInput(attrs={"class": "staff-input"}))
    option_2 = forms.CharField(label="Option B", required=False, widget=forms.TextInput(attrs={"class": "staff-input"}))
    option_3 = forms.CharField(label="Option C", required=False, widget=forms.TextInput(attrs={"class": "staff-input"}))
    option_4 = forms.CharField(label="Option D", required=False, widget=forms.TextInput(attrs={"class": "staff-input"}))
    correct_option = forms.ChoiceField(
        label="Correct answer",
        choices=[(1, "A"), (2, "B"), (3, "C"), (4, "D")],
        required=False,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )

    class Meta:
        model = SkillLesson
        fields = [
            "skill",
            "level",
            "title",
            "slug",
            "sort_order",
            "is_published",
            "passage",
            "question_prompt",
            "writing_prompt",
            "min_words",
            "max_words",
            "vocab_word",
            "vocab_ipa",
            "vocab_meaning",
            "vocab_example",
            "vocab_cefr",
        ]
        widgets = {
            "skill": forms.Select(attrs={"class": "staff-input"}),
            "level": forms.NumberInput(attrs={"class": "staff-input", "min": 1, "max": 15}),
            "title": forms.TextInput(attrs={"class": "staff-input"}),
            "slug": forms.TextInput(attrs={"class": "staff-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "staff-input", "min": 0}),
            "is_published": forms.CheckboxInput(attrs={"class": "staff-checkbox"}),
            "passage": forms.Textarea(attrs={"class": "staff-input staff-textarea", "rows": 8}),
            "question_prompt": forms.Textarea(attrs={"class": "staff-input staff-textarea", "rows": 3}),
            "writing_prompt": forms.Textarea(attrs={"class": "staff-input staff-textarea", "rows": 5}),
            "min_words": forms.NumberInput(attrs={"class": "staff-input", "min": 1}),
            "max_words": forms.NumberInput(attrs={"class": "staff-input", "min": 1}),
            "vocab_word": forms.TextInput(attrs={"class": "staff-input"}),
            "vocab_ipa": forms.TextInput(attrs={"class": "staff-input"}),
            "vocab_meaning": forms.Textarea(attrs={"class": "staff-input staff-textarea", "rows": 3}),
            "vocab_example": forms.Textarea(attrs={"class": "staff-input staff-textarea", "rows": 2}),
            "vocab_cefr": forms.TextInput(attrs={"class": "staff-input", "placeholder": "B2"}),
        }

    def __init__(self, *args, skill_slug: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skill"].queryset = Skill.objects.filter(slug__in=STAFF_SKILL_SLUGS).order_by("name")
        if skill_slug:
            self.fields["skill"].initial = Skill.objects.filter(slug=skill_slug).first()
            self.fields["skill"].widget = forms.HiddenInput()

        if self.instance and self.instance.pk:
            options = self.instance.options if isinstance(self.instance.options, list) else []
            for idx in range(4):
                key = f"option_{idx + 1}"
                if idx < len(options):
                    self.fields[key].initial = options[idx]
            if self.instance.correct_index is not None:
                self.fields["correct_option"].initial = self.instance.correct_index + 1

    def clean_level(self):
        level = self.cleaned_data.get("level")
        if level is not None and (level < 1 or level > 15):
            raise ValidationError("Level must be between 1 and 15.")
        return level

    def clean(self):
        cleaned = super().clean()
        skill = cleaned.get("skill")
        if not skill:
            return cleaned

        slug = cleaned.get("slug") or ""
        if not slug and cleaned.get("title"):
            cleaned["slug"] = slugify(cleaned["title"])[:80]
        elif not slug:
            self.add_error("slug", "Slug is required.")

        skill_slug = skill.slug
        if skill_slug in {"reading", "listening"}:
            options = [cleaned.get(f"option_{i}", "").strip() for i in range(1, 5)]
            options = [o for o in options if o]
            if len(options) < 2:
                raise ValidationError("Quiz skills need at least two answer options.")
            if not cleaned.get("question_prompt", "").strip():
                raise ValidationError("Question prompt is required for quiz skills.")
            if skill_slug == "reading" and not cleaned.get("passage", "").strip():
                raise ValidationError("Passage is required for reading lessons.")
            correct = int(cleaned.get("correct_option") or 1)
            if correct < 1 or correct > len(options):
                raise ValidationError("Correct answer must match one of the filled options.")
            cleaned["_packed_options"] = options
            cleaned["_correct_index"] = correct - 1
        elif skill_slug == "writing":
            if not cleaned.get("writing_prompt", "").strip():
                raise ValidationError("Writing prompt is required.")
        elif skill_slug == "vocabulary":
            if not cleaned.get("vocab_word", "").strip():
                raise ValidationError("Vocabulary word is required.")
            if not cleaned.get("vocab_meaning", "").strip():
                raise ValidationError("Word meaning is required.")

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        skill = self.cleaned_data.get("skill")
        if skill and skill.slug in {"reading", "listening"}:
            instance.options = self.cleaned_data.get("_packed_options", [])
            instance.correct_index = self.cleaned_data.get("_correct_index", 0)
        if not instance.sort_order:
            last = (
                SkillLesson.objects.filter(skill=instance.skill)
                .order_by("-sort_order")
                .values_list("sort_order", flat=True)
                .first()
            )
            instance.sort_order = (last or 0) + 1
        if commit:
            instance.save()
            self.save_m2m()
        return instance
