from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from ortools.sat.python import cp_model

from app.core.config import get_settings
from app.models.schedule import (
    AssignmentInput,
    AvailabilityType,
    ScheduleEntryOutput,
    ScheduleSolveRequest,
    ScheduleSolveResponse,
    SolverResultStatus,
    SolverStatisticsOutput,
)


@dataclass(frozen=True)
class Slot:
    day_of_week: int
    period_id: str
    shift_id: str
    period_number: int


VariableKey = tuple[
    str,
    int,
    int,
    str,
]


def solve_schedule(
    request: ScheduleSolveRequest,
) -> ScheduleSolveResponse:
    settings = get_settings()

    model = cp_model.CpModel()

    groups_by_id = {
        group.id: group
        for group in request.groups
    }

    teachers_by_id = {
        teacher.id: teacher
        for teacher in request.teachers
    }

    periods_by_id = {
        period.id: period
        for period in request.shift_periods
    }

    class_periods_by_shift: dict[
        str,
        list,
    ] = defaultdict(list)

    for period in request.shift_periods:
        if period.period_type == "class":
            class_periods_by_shift[
                period.shift_id
            ].append(period)

    for periods in (
        class_periods_by_shift.values()
    ):
        periods.sort(
            key=lambda period:
                period.period_number
        )

    availability_map = {
        (
            availability.teacher_id,
            availability.day_of_week,
            availability.shift_period_id,
        ): availability
        for availability
        in request.teacher_availability
    }

    locked_entries_map = {
        (
            entry.assignment_id,
            entry.occurrence_number,
        ): entry
        for entry in request.locked_entries
    }

    assignment_variables: dict[
        VariableKey,
        cp_model.IntVar,
    ] = {}

    variables_by_group_slot: dict[
        tuple[str, int, str],
        list[cp_model.IntVar],
    ] = defaultdict(list)

    variables_by_teacher_slot: dict[
        tuple[str, int, str],
        list[cp_model.IntVar],
    ] = defaultdict(list)

    variables_by_assignment_day: dict[
        tuple[str, int],
        list[cp_model.IntVar],
    ] = defaultdict(list)

    objective_terms: list = []
    warnings: list[str] = []

    # =====================================================
    # VALIDACIONES INICIALES
    # =====================================================

    for assignment in request.assignments:
        if (
            assignment.group_id
            not in groups_by_id
        ):
            return infeasible_response(
                message=(
                    "La asignación "
                    f"{assignment.id} pertenece "
                    "a un grupo inexistente."
                ),
                total_required_entries=(
                    get_total_occurrences(
                        request.assignments
                    )
                ),
            )

        if (
            assignment.teacher_id
            not in teachers_by_id
        ):
            return infeasible_response(
                message=(
                    "La asignación "
                    f"{assignment.id} pertenece "
                    "a un profesor inexistente."
                ),
                total_required_entries=(
                    get_total_occurrences(
                        request.assignments
                    )
                ),
            )

    # =====================================================
    # CREACIÓN DE VARIABLES
    # =====================================================

    for assignment in request.assignments:
        group = groups_by_id[
            assignment.group_id
        ]

        valid_periods = (
            class_periods_by_shift.get(
                group.shift_id,
                [],
            )
        )

        period_rank_by_id = {
            period.id: index
            for index, period
            in enumerate(valid_periods)
        }

        valid_slots = [
            Slot(
                day_of_week=day,
                period_id=period.id,
                shift_id=period.shift_id,
                period_number=(
                    period.period_number
                ),
            )
            for day in request.days
            for period in valid_periods
        ]

        if (
            len(valid_slots)
            < assignment.weekly_periods
        ):
            return infeasible_response(
                message=(
                    f"La asignación {assignment.id} "
                    f"requiere "
                    f"{assignment.weekly_periods} "
                    "horas, pero solamente tiene "
                    f"{len(valid_slots)} espacios."
                ),
                total_required_entries=(
                    get_total_occurrences(
                        request.assignments
                    )
                ),
            )

        for occurrence_number in range(
            1,
            assignment.weekly_periods + 1,
        ):
            locked_entry = (
                locked_entries_map.get(
                    (
                        assignment.id,
                        occurrence_number,
                    )
                )
            )

            occurrence_variables: list[
                cp_model.IntVar
            ] = []

            for slot in valid_slots:
                availability = (
                    availability_map.get(
                        (
                            assignment.teacher_id,
                            slot.day_of_week,
                            slot.period_id,
                        )
                    )
                )

                if (
                    availability
                    and (
                        availability
                        .availability_type
                        == AvailabilityType
                        .UNAVAILABLE
                    )
                ):
                    continue

                variable_key = (
                    assignment.id,
                    occurrence_number,
                    slot.day_of_week,
                    slot.period_id,
                )

                variable = (
                    model.new_bool_var(
                        (
                            "assign_"
                            f"{assignment.id}_"
                            f"{occurrence_number}_"
                            f"{slot.day_of_week}_"
                            f"{slot.period_id}"
                        )
                    )
                )

                assignment_variables[
                    variable_key
                ] = variable

                occurrence_variables.append(
                    variable
                )

                variables_by_group_slot[
                    (
                        assignment.group_id,
                        slot.day_of_week,
                        slot.period_id,
                    )
                ].append(variable)

                variables_by_teacher_slot[
                    (
                        assignment.teacher_id,
                        slot.day_of_week,
                        slot.period_id,
                    )
                ].append(variable)

                variables_by_assignment_day[
                    (
                        assignment.id,
                        slot.day_of_week,
                    )
                ].append(variable)

                preference_score = (
                    get_preference_score(
                        availability_type=(
                            availability
                            .availability_type
                            if availability
                            else (
                                AvailabilityType
                                .AVAILABLE
                            )
                        ),
                        request=request,
                    )
                )

                if (
                    request.options
                    .optimize_preferences
                ):
                    if preference_score != 0:
                        objective_terms.append(
                            preference_score
                            * variable
                        )

                    # Optimización ligera:
                    # favorece las primeras horas
                    # sin crear variables auxiliares.
                    period_rank = (
                        period_rank_by_id.get(
                            slot.period_id,
                            0,
                        )
                    )

                    late_period_penalty = (
                        request.options
                        .penalize_late_period
                        * period_rank
                    )

                    if (
                        late_period_penalty
                        > 0
                    ):
                        objective_terms.append(
                            -late_period_penalty
                            * variable
                        )

                if locked_entry:
                    should_be_locked_here = (
                        locked_entry
                        .day_of_week
                        == slot.day_of_week
                        and (
                            locked_entry
                            .shift_period_id
                            == slot.period_id
                        )
                    )

                    model.add(
                        variable
                        == int(
                            should_be_locked_here
                        )
                    )

            if not occurrence_variables:
                return infeasible_response(
                    message=(
                        "La ocurrencia "
                        f"{occurrence_number} de "
                        f"la asignación "
                        f"{assignment.id} no tiene "
                        "ningún espacio disponible."
                    ),
                    total_required_entries=(
                        get_total_occurrences(
                            request.assignments
                        )
                    ),
                )

            # Cada clase debe colocarse
            # exactamente una vez.
            model.add_exactly_one(
                occurrence_variables
            )

    # =====================================================
    # NO EMPALMES
    # =====================================================

    for variables in (
        variables_by_group_slot.values()
    ):
        model.add_at_most_one(
            variables
        )

    for variables in (
        variables_by_teacher_slot.values()
    ):
        model.add_at_most_one(
            variables
        )

    # =====================================================
    # MÁXIMO DIARIO Y MÍNIMO DE DÍAS POR ASIGNACIÓN
    # =====================================================

    for assignment in request.assignments:
        used_day_variables: list[
            cp_model.IntVar
        ] = []

        for day in request.days:
            daily_variables = (
                variables_by_assignment_day
                .get(
                    (
                        assignment.id,
                        day,
                    ),
                    [],
                )
            )

            if not daily_variables:
                continue

            model.add(
                sum(daily_variables)
                <= (
                    assignment
                    .max_periods_per_day
                )
            )

            used_day = (
                model.new_bool_var(
                    (
                        "used_day_"
                        f"{assignment.id}_"
                        f"{day}"
                    )
                )
            )

            model.add(
                sum(daily_variables)
                >= used_day
            )

            model.add(
                sum(daily_variables)
                <= (
                    assignment
                    .max_periods_per_day
                    * used_day
                )
            )

            used_day_variables.append(
                used_day
            )

        if (
            len(used_day_variables)
            < assignment.min_days_per_week
        ):
            return infeasible_response(
                message=(
                    f"La asignación {assignment.id} "
                    "exige "
                    f"{assignment.min_days_per_week} "
                    "días, pero no dispone de "
                    "suficientes días utilizables."
                ),
                total_required_entries=(
                    get_total_occurrences(
                        request.assignments
                    )
                ),
            )

        model.add(
            sum(used_day_variables)
            >= assignment.min_days_per_week
        )

    # =====================================================
    # CARGA TOTAL Y DIARIA POR PROFESOR
    # =====================================================

    assignments_by_teacher: dict[
        str,
        list[AssignmentInput],
    ] = defaultdict(list)

    assignment_ids_by_teacher: dict[
        str,
        set[str],
    ] = defaultdict(set)

    for assignment in request.assignments:
        assignments_by_teacher[
            assignment.teacher_id
        ].append(assignment)

        assignment_ids_by_teacher[
            assignment.teacher_id
        ].add(assignment.id)

    for (
        teacher_id,
        teacher_assignments,
    ) in assignments_by_teacher.items():
        del teacher_assignments

        teacher = teachers_by_id[
            teacher_id
        ]

        teacher_assignment_ids = (
            assignment_ids_by_teacher[
                teacher_id
            ]
        )

        teacher_weekly_variables = [
            variable
            for (
                assignment_id,
                _occurrence,
                _day,
                _period,
            ), variable
            in assignment_variables.items()
            if (
                assignment_id
                in teacher_assignment_ids
            )
        ]

        if teacher_weekly_variables:
            model.add(
                sum(
                    teacher_weekly_variables
                )
                <= (
                    teacher
                    .max_weekly_periods
                )
            )

        for day in request.days:
            teacher_daily_variables = [
                variable
                for (
                    assignment_id,
                    _occurrence,
                    variable_day,
                    _period,
                ), variable
                in assignment_variables.items()
                if (
                    variable_day == day
                    and (
                        assignment_id
                        in teacher_assignment_ids
                    )
                )
            ]

            if teacher_daily_variables:
                model.add(
                    sum(
                        teacher_daily_variables
                    )
                    <= (
                        teacher
                        .max_daily_periods
                    )
                )

    # =====================================================
    # EVITAR DOS OCURRENCIAS DE LA MISMA ASIGNACIÓN
    # EN LA MISMA HORA
    # =====================================================

    occurrences_by_assignment_slot: dict[
        tuple[str, int, str],
        list[cp_model.IntVar],
    ] = defaultdict(list)

    for (
        assignment_id,
        _occurrence_number,
        day_of_week,
        period_id,
    ), variable in (
        assignment_variables.items()
    ):
        occurrences_by_assignment_slot[
            (
                assignment_id,
                day_of_week,
                period_id,
            )
        ].append(variable)

    for variables in (
        occurrences_by_assignment_slot
        .values()
    ):
        model.add_at_most_one(
            variables
        )

    # =====================================================
    # PREFERENCIA POR BLOQUES CONSECUTIVOS
    # =====================================================

    if (
        request.options
        .optimize_preferences
    ):
        for assignment in (
            request.assignments
        ):
            if (
                not (
                    assignment
                    .allow_consecutive_periods
                )
                or (
                    assignment
                    .preferred_block_size
                    <= 1
                )
            ):
                continue

            add_consecutive_block_preferences(
                model=model,
                assignment=assignment,
                request=request,
                groups_by_id=groups_by_id,
                class_periods_by_shift=(
                    class_periods_by_shift
                ),
                assignment_variables=(
                    assignment_variables
                ),
                objective_terms=(
                    objective_terms
                ),
            )

    # =====================================================
    # FUNCIÓN OBJETIVO
    # =====================================================

    if (
        request.options
        .optimize_preferences
        and objective_terms
    ):
        model.maximize(
            sum(objective_terms)
        )

    # =====================================================
    # RESOLVER
    # =====================================================

    solver = cp_model.CpSolver()

    solver.parameters.max_time_in_seconds = (
        request.options.max_time_seconds
        or (
            settings
            .solver_max_time_seconds
        )
    )

    solver.parameters.num_search_workers = (
        request.options.num_workers
        or settings.solver_num_workers
    )

    solver.parameters.random_seed = (
        request.options.random_seed
    )

    status = solver.solve(model)

    mapped_status = map_solver_status(
        status
    )

    statistics = (
        SolverStatisticsOutput(
            conflicts=solver.num_conflicts,
            branches=solver.num_branches,
            wall_time_seconds=(
                solver.wall_time
            ),
            objective_value=(
                solver.objective_value
                if (
                    mapped_status
                    in {
                        SolverResultStatus
                        .OPTIMAL,
                        SolverResultStatus
                        .FEASIBLE,
                    }
                    and objective_terms
                )
                else None
            ),
            best_objective_bound=(
                solver.best_objective_bound
                if (
                    mapped_status
                    in {
                        SolverResultStatus
                        .OPTIMAL,
                        SolverResultStatus
                        .FEASIBLE,
                    }
                    and objective_terms
                )
                else None
            ),
            scheduled_entries=0,
            total_required_entries=(
                get_total_occurrences(
                    request.assignments
                )
            ),
        )
    )

    if mapped_status not in {
        SolverResultStatus.OPTIMAL,
        SolverResultStatus.FEASIBLE,
    }:
        return ScheduleSolveResponse(
            status=mapped_status,
            message=get_status_message(
                mapped_status
            ),
            entries=[],
            statistics=statistics,
            warnings=warnings,
        )

    # =====================================================
    # CONSTRUIR RESULTADO
    # =====================================================

    entries: list[
        ScheduleEntryOutput
    ] = []

    assignments_by_id = {
        assignment.id: assignment
        for assignment
        in request.assignments
    }

    for (
        assignment_id,
        occurrence_number,
        day_of_week,
        period_id,
    ), variable in (
        assignment_variables.items()
    ):
        if not solver.boolean_value(
            variable
        ):
            continue

        assignment = assignments_by_id[
            assignment_id
        ]

        availability = (
            availability_map.get(
                (
                    assignment.teacher_id,
                    day_of_week,
                    period_id,
                )
            )
        )

        preference_score = (
            get_preference_score(
                availability_type=(
                    availability
                    .availability_type
                    if availability
                    else (
                        AvailabilityType
                        .AVAILABLE
                    )
                ),
                request=request,
            )
        )

        entries.append(
            ScheduleEntryOutput(
                assignment_id=(
                    assignment.id
                ),
                occurrence_number=(
                    occurrence_number
                ),
                group_id=(
                    assignment.group_id
                ),
                subject_id=(
                    assignment.subject_id
                ),
                teacher_id=(
                    assignment.teacher_id
                ),
                day_of_week=(
                    day_of_week
                ),
                shift_period_id=(
                    period_id
                ),
                preference_score=(
                    preference_score
                ),
                locked=(
                    (
                        assignment.id,
                        occurrence_number,
                    )
                    in locked_entries_map
                ),
            )
        )

    entries.sort(
        key=lambda entry: (
            entry.day_of_week,
            periods_by_id[
                entry.shift_period_id
            ].period_number,
            entry.group_id,
            entry.subject_id,
        )
    )

    statistics.scheduled_entries = (
        len(entries)
    )

    return ScheduleSolveResponse(
        status=mapped_status,
        message=get_status_message(
            mapped_status
        ),
        entries=entries,
        statistics=statistics,
        warnings=warnings,
    )


def add_consecutive_block_preferences(
    *,
    model: cp_model.CpModel,
    assignment: AssignmentInput,
    request: ScheduleSolveRequest,
    groups_by_id: dict,
    class_periods_by_shift: dict,
    assignment_variables: dict[
        VariableKey,
        cp_model.IntVar,
    ],
    objective_terms: list,
) -> None:
    """
    Agrega una recompensa pequeña por colocar dos
    clases de la misma asignación en horas consecutivas.

    No obliga a crear bloques. Solamente los favorece
    cuando también se cumplen las restricciones duras.
    """

    group = groups_by_id[
        assignment.group_id
    ]

    ordered_periods = (
        class_periods_by_shift.get(
            group.shift_id,
            [],
        )
    )

    occurrence_numbers = range(
        1,
        assignment.weekly_periods + 1,
    )

    for day in request.days:
        for (
            first_period,
            second_period,
        ) in zip(
            ordered_periods,
            ordered_periods[1:],
        ):
            if (
                second_period.period_number
                != (
                    first_period
                    .period_number
                    + 1
                )
            ):
                continue

            first_slot_variables = [
                assignment_variables.get(
                    (
                        assignment.id,
                        occurrence_number,
                        day,
                        first_period.id,
                    )
                )
                for occurrence_number
                in occurrence_numbers
            ]

            second_slot_variables = [
                assignment_variables.get(
                    (
                        assignment.id,
                        occurrence_number,
                        day,
                        second_period.id,
                    )
                )
                for occurrence_number
                in occurrence_numbers
            ]

            first_slot_variables = [
                variable
                for variable
                in first_slot_variables
                if variable is not None
            ]

            second_slot_variables = [
                variable
                for variable
                in second_slot_variables
                if variable is not None
            ]

            if (
                not first_slot_variables
                or not second_slot_variables
            ):
                continue

            first_used = (
                model.new_bool_var(
                    (
                        "block_first_"
                        f"{assignment.id}_"
                        f"{day}_"
                        f"{first_period.id}"
                    )
                )
            )

            second_used = (
                model.new_bool_var(
                    (
                        "block_second_"
                        f"{assignment.id}_"
                        f"{day}_"
                        f"{second_period.id}"
                    )
                )
            )

            # Por las restricciones anteriores,
            # cada suma puede valer solamente 0 o 1.
            model.add(
                sum(first_slot_variables)
                == first_used
            )

            model.add(
                sum(second_slot_variables)
                == second_used
            )

            consecutive_pair = (
                model.new_bool_var(
                    (
                        "consecutive_"
                        f"{assignment.id}_"
                        f"{day}_"
                        f"{first_period.id}_"
                        f"{second_period.id}"
                    )
                )
            )

            model.add(
                consecutive_pair
                <= first_used
            )

            model.add(
                consecutive_pair
                <= second_used
            )

            model.add(
                consecutive_pair
                >= (
                    first_used
                    + second_used
                    - 1
                )
            )

            # Peso fijo moderado. No depende de una
            # propiedad opcional del modelo Pydantic.
            objective_terms.append(
                15 * consecutive_pair
            )


def get_preference_score(
    *,
    availability_type:
        AvailabilityType,
    request:
        ScheduleSolveRequest,
) -> int:
    if (
        availability_type
        == AvailabilityType.PREFERRED
    ):
        return (
            request.options
            .reward_preferred
        )

    if (
        availability_type
        == AvailabilityType.REQUIRED
    ):
        return (
            request.options
            .reward_required
        )

    if (
        availability_type
        == AvailabilityType.AVOID
    ):
        return -(
            request.options
            .penalize_avoid
        )

    return 0


def get_total_occurrences(
    assignments:
        Iterable[AssignmentInput],
) -> int:
    return sum(
        assignment.weekly_periods
        for assignment in assignments
    )


def map_solver_status(
    status: cp_model.CpSolverStatus,
) -> SolverResultStatus:
    mapping = {
        cp_model.OPTIMAL:
            SolverResultStatus.OPTIMAL,

        cp_model.FEASIBLE:
            SolverResultStatus.FEASIBLE,

        cp_model.INFEASIBLE:
            SolverResultStatus.INFEASIBLE,

        cp_model.MODEL_INVALID:
            SolverResultStatus.MODEL_INVALID,

        cp_model.UNKNOWN:
            SolverResultStatus.UNKNOWN,
    }

    return mapping.get(
        status,
        SolverResultStatus.ERROR,
    )


def get_status_message(
    status: SolverResultStatus,
) -> str:
    messages = {
        SolverResultStatus.OPTIMAL:
            "Se encontró una solución óptima.",

        SolverResultStatus.FEASIBLE:
            "Se encontró una solución válida.",

        SolverResultStatus.INFEASIBLE:
            (
                "No existe una solución que cumpla "
                "todas las restricciones."
            ),

        SolverResultStatus.MODEL_INVALID:
            (
                "El modelo de optimización "
                "no es válido."
            ),

        SolverResultStatus.UNKNOWN:
            (
                "El solver terminó sin determinar "
                "una solución."
            ),

        SolverResultStatus.ERROR:
            (
                "Ocurrió un error durante "
                "la optimización."
            ),
    }

    return messages[status]


def infeasible_response(
    *,
    message: str,
    total_required_entries: int,
) -> ScheduleSolveResponse:
    return ScheduleSolveResponse(
        status=(
            SolverResultStatus
            .INFEASIBLE
        ),
        message=message,
        entries=[],
        statistics=(
            SolverStatisticsOutput(
                scheduled_entries=0,
                total_required_entries=(
                    total_required_entries
                ),
            )
        ),
        warnings=[],
    )