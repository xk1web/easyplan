export interface PreviousMonthStats {
  total_hours?: Record<string, number>;
  saturdays_worked?: Record<string, number>;
}

export interface PlanningRequest {
  employees: string[];
  contracts: number[];
  roles: string[];
  days: string[];
  unavailabilities?: number[][];
  config?: Record<string, unknown>;
  previous_month_stats?: PreviousMonthStats;
}

export interface SolverMetrics {
  num_variables: number;
  num_constraints: number;
  solver_wall_time: number;
  solve_time_seconds?: number;
  solver_status: string;
  gap_percent?: number;
  warnings?: string[];
  objective_value?: number;
  total_internal_hours?: number;
}

export interface TimeRange {
  start: string;
  end: string;
}

export interface DaySchedule {
  ranges: TimeRange[];
  hours: number;
}

export interface EmployeeSchedule {
  days: Record<string, DaySchedule>;
  total_hours: number;
}

export interface GlobalKPI {
  total_contracted_hours: number
  total_worked_hours: number
  total_internal_hours: number
  total_coverage_hours: number
  coverage_gap: number
  overstaff_hours: number
}

export interface PlanningResponse {
  status: string;
  schedule?: Record<string, EmployeeSchedule> | null;
  solver_time: number;
  solve_time_seconds?: number;
  metrics?: SolverMetrics | null;
  kpi: GlobalKPI;
  error?: string | null;
  total_overtime_used_hours?: number | null;
  capacity_total_hours?: number | null;
  coverage_total_hours?: number | null;
  hours_per_employee?: Record<string, number> | null;
  suggestions?: string[] | null;
  classification?: string | null;
}
