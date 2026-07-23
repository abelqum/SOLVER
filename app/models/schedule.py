from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Identifier = Annotated[str, Field(min_length=1, max_length=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class AvailabilityType(StrEnum):
    AVAILABLE = "available"
    PREFERRED = "preferred"
    AVOID = "avoid"
    REQUIRED = "required"
    UNAVAILABLE = "unavailable"


class SolverResultStatus(StrEnum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    MODEL_INVALID = "model_invalid"
    UNKNOWN = "unknown"
    ERROR = "error"


class ShiftPeriodInput(StrictModel):
    id: Identifier
    shift_id: Identifier
    period_number: Annotated[int, Field(ge=1)]
    name: Annotated[str, Field(min_length=1, max_length=100)]
    start_time: Annotated[str, Field(pattern=r"^\d{2}:\d{2}(:\d{2})?$")]
    end_time: Annotated[str, Field(pattern=r"^\d{2}:\d{2}(:\d{2})?$")]
    period_type: Literal["class", "recess", "unavailable"] = "class"


class GroupInput(StrictModel):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=50)]
    grade_level_id: Identifier
    shift_id: Identifier


class TeacherInput(StrictModel):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=250)]
    max_weekly_periods: Annotated[int, Field(ge=1, le=200)]
    max_daily_periods: Annotated[int, Field(ge=1, le=50)]


class AssignmentInput(StrictModel):
    id: Identifier
    group_id: Identifier
    subject_id: Identifier
    teacher_id: Identifier

    weekly_periods: Annotated[int, Field(ge=1, le=100)]
    max_periods_per_day: Annotated[int, Field(ge=1, le=20)]
    min_days_per_week: Annotated[int, Field(ge=1, le=7)]

    allow_consecutive_periods: bool = False
    preferred_block_size: Annotated[int, Field(ge=1, le=10)] = 1

    @model_validator(mode="after")
    def validate_assignment(self) -> "AssignmentInput":
        if self.min_days_per_week > self.weekly_periods:
            raise ValueError(
                "min_days_per_week no puede superar weekly_periods."
            )

        if self.max_periods_per_day > self.weekly_periods:
            raise ValueError(
                "max_periods_per_day no puede superar weekly_periods."
            )

        if self.preferred_block_size > self.max_periods_per_day:
            raise ValueError(
                "preferred_block_size no puede superar "
                "max_periods_per_day."
            )

        if (
            not self.allow_consecutive_periods
            and self.preferred_block_size > 1
        ):
            raise ValueError(
                "Los bloques mayores a uno requieren "
                "allow_consecutive_periods=true."
            )

        return self


class TeacherAvailabilityInput(StrictModel):
    teacher_id: Identifier
    day_of_week: Annotated[int, Field(ge=1, le=7)]
    shift_period_id: Identifier
    availability_type: AvailabilityType = AvailabilityType.AVAILABLE
    weight: Annotated[int, Field(ge=-1000, le=1000)] = 0


class LockedEntryInput(StrictModel):
    assignment_id: Identifier
    occurrence_number: Annotated[int, Field(ge=1)]
    day_of_week: Annotated[int, Field(ge=1, le=7)]
    shift_period_id: Identifier
class SolverOptionsInput(StrictModel):
    max_time_seconds: Annotated[
        float,
        Field(gt=0, le=600),
    ] | None = None

    num_workers: Annotated[
        int,
        Field(ge=1, le=64),
    ] | None = None

    optimize_preferences: bool = True

    random_seed: Annotated[
        int,
        Field(ge=0),
    ] = 0

    penalize_avoid: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 80

    reward_preferred: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 40

    reward_required: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 100

    # Favorece las primeras horas sin crear
    # variables adicionales de compactación.
    penalize_late_period: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 4

    # Se conserva por compatibilidad con el
    # payload actual.
    penalize_isolated_teacher_period: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 2
    max_time_seconds: Annotated[
        float,
        Field(gt=0, le=600),
    ] | None = None

    num_workers: Annotated[
        int,
        Field(ge=1, le=64),
    ] | None = None

    optimize_preferences: bool = True

    random_seed: Annotated[
        int,
        Field(ge=0),
    ] = 0

    # Disponibilidad docente.
    penalize_avoid: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 80

    reward_preferred: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 40

    reward_required: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 100

    # Compactación de horarios.
    penalize_group_gap: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 30

    penalize_teacher_gap: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 20

    penalize_late_group_period: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 3

    penalize_isolated_teacher_period: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 5

    reward_consecutive_assignment_periods: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 15
    max_time_seconds: Annotated[float, Field(gt=0, le=600)] | None = None
    num_workers: Annotated[int, Field(ge=1, le=64)] | None = None

    optimize_preferences: bool = True
    random_seed: Annotated[int, Field(ge=0)] = 0

    penalize_avoid: Annotated[int, Field(ge=0, le=10000)] = 80
    reward_preferred: Annotated[int, Field(ge=0, le=10000)] = 40
    reward_required: Annotated[int, Field(ge=0, le=10000)] = 100

    penalize_isolated_teacher_period: Annotated[
        int,
        Field(ge=0, le=10000),
    ] = 2


class ScheduleSolveRequest(StrictModel):
    school_id: Identifier
    academic_period_id: Identifier

    days: list[Annotated[int, Field(ge=1, le=7)]] = Field(
        default_factory=lambda: [1, 2, 3, 4, 5],
        min_length=1,
        max_length=7,
    )

    shift_periods: list[ShiftPeriodInput] = Field(min_length=1)
    groups: list[GroupInput] = Field(min_length=1)
    teachers: list[TeacherInput] = Field(min_length=1)
    assignments: list[AssignmentInput] = Field(min_length=1)

    teacher_availability: list[TeacherAvailabilityInput] = Field(
        default_factory=list
    )

    locked_entries: list[LockedEntryInput] = Field(
        default_factory=list
    )

    options: SolverOptionsInput = Field(
        default_factory=SolverOptionsInput
    )

    @model_validator(mode="after")
    def validate_references(self) -> "ScheduleSolveRequest":
        if len(set(self.days)) != len(self.days):
            raise ValueError("La lista days contiene valores duplicados.")

        period_ids = {
            period.id
            for period in self.shift_periods
        }

        group_ids = {
            group.id
            for group in self.groups
        }

        teacher_ids = {
            teacher.id
            for teacher in self.teachers
        }

        assignment_ids = {
            assignment.id
            for assignment in self.assignments
        }

        if len(period_ids) != len(self.shift_periods):
            raise ValueError(
                "Existen horas duplicadas."
            )

        if len(group_ids) != len(self.groups):
            raise ValueError(
                "Existen grupos duplicados."
            )

        if len(teacher_ids) != len(self.teachers):
            raise ValueError(
                "Existen profesores duplicados."
            )

        if len(assignment_ids) != len(self.assignments):
            raise ValueError(
                "Existen asignaciones duplicadas."
            )

        groups_by_id = {
            group.id: group
            for group in self.groups
        }

        for assignment in self.assignments:
            if assignment.group_id not in group_ids:
                raise ValueError(
                    f"La asignación {assignment.id} referencia "
                    "un grupo inexistente."
                )

            if assignment.teacher_id not in teacher_ids:
                raise ValueError(
                    f"La asignación {assignment.id} referencia "
                    "un profesor inexistente."
                )

            group = groups_by_id[assignment.group_id]

            has_shift_periods = any(
                period.shift_id == group.shift_id
                and period.period_type == "class"
                for period in self.shift_periods
            )

            if not has_shift_periods:
                raise ValueError(
                    f"El grupo {group.name} no tiene horas "
                    "de clase disponibles."
                )

        for availability in self.teacher_availability:
            if availability.teacher_id not in teacher_ids:
                raise ValueError(
                    "Una disponibilidad referencia un profesor "
                    "inexistente."
                )

            if availability.shift_period_id not in period_ids:
                raise ValueError(
                    "Una disponibilidad referencia una hora "
                    "inexistente."
                )

        for locked_entry in self.locked_entries:
            if locked_entry.assignment_id not in assignment_ids:
                raise ValueError(
                    "Una entrada bloqueada referencia una "
                    "asignación inexistente."
                )

            if locked_entry.shift_period_id not in period_ids:
                raise ValueError(
                    "Una entrada bloqueada referencia una "
                    "hora inexistente."
                )

        return self


class ScheduleEntryOutput(StrictModel):
    assignment_id: Identifier
    occurrence_number: int

    group_id: Identifier
    subject_id: Identifier
    teacher_id: Identifier

    day_of_week: int
    shift_period_id: Identifier

    preference_score: int = 0
    locked: bool = False


class SolverStatisticsOutput(StrictModel):
    conflicts: int = 0
    branches: int = 0
    wall_time_seconds: float = 0
    objective_value: float | None = None
    best_objective_bound: float | None = None

    scheduled_entries: int = 0
    total_required_entries: int = 0


class ScheduleSolveResponse(StrictModel):
    status: SolverResultStatus
    message: str

    entries: list[ScheduleEntryOutput] = Field(
        default_factory=list
    )

    statistics: SolverStatisticsOutput

    warnings: list[str] = Field(default_factory=list)