export interface CaseMetrics {
  respondent_count: number;
  total_case_age_days: number;
  total_hearings_scheduled: number;
  current_stage_duration_days: number;
}

export interface CaseHistoryEntry {
  judge_title: string;
  business_on_date: string;
  hearing_date: string;
  purpose_of_hearing: string;
}

/* An order recorded against the case by the case service — the court's
   own record of what it has passed, not a document somebody uploaded. */
export interface CaseOrder {
  order_type: string;
  order_number: string;
  order_date: string;
  order_details: string;
  order_section: string;
}

/* Where the record came from. Every non-session case carries this, so
   the screen can say plainly that it is reading development data
   rather than a live court feed. */
export interface CaseDataSource {
  provider: string;
  label: string;
  live_ecourts_data: boolean;
  disclaimer: string;
  available?: boolean;
  records?: number;
}

/* One step of the case's history as the case service orders it:
   filing, registration, a sitting, a passed order, the next listing —
   oldest first, and only ever built from dates the record carries.
   `date` is empty when the source row had none of its own. */
export interface CaseTimelineEvent {
  date: string;
  event: string;
  description: string;
  purpose: string;
  stage: string | null;
}

export interface Case {
  cnr_number: string;

  /* Account this record belongs to. The My Cases screen filters on it so a
     signed-in user only ever sees their own cases — never the full set. */
  owner_user_id: string;

  /* Advocate handling the matter. The lawyer's Active Cases screen filters
     on it, so one lawyer never sees another's caseload. */
  handling_lawyer_id: string;

  court_state: string;
  court_district: string;
  court_name: string;
  case_type: string;
  filing_number: string;
  filing_date: string;
  registration_number: string;
  registration_date: string;
  first_hearing_date: string;
  next_hearing_date: string;
  current_case_stage: string;
  presiding_judge: string;
  petitioner_name: string;
  petitioner_advocate: string;
  respondents_list: string[];
  applied_act: string;
  applied_section: string;

  /* "Case pending" / "Case disposed" exactly as the source records it.
     Optional: cases saved from the browser's store have no such field. */
  case_status?: string;

  calculated_metrics: CaseMetrics;
  case_history_timeline: CaseHistoryEntry[];

  /* Present only on records read from the case service. Cases saved
     from the browser's store have no court-recorded orders behind them. */
  orders?: CaseOrder[];
  data_source?: CaseDataSource;

  /* The full journey — filed, registered, every sitting, every order,
     the next date — sorted oldest first. Store-saved cases have no
     court record to draw it from, so it is optional. */
  timeline?: CaseTimelineEvent[];
}