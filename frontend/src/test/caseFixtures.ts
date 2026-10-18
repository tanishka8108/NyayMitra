import type { Case } from "../types/case";

/* One ordinary development record, shaped exactly as
   `GET /api/cases/cnr/{cnr}` answers. Tests override the parts they
   are about — a disposed case, a record with no district, orders —
   rather than each keeping its own copy of the whole thing. */
export function makeCase(overrides: Partial<Case> = {}): Case {
  const record: Case = {
    cnr_number: "MHPU210000042026",
    owner_user_id: "USER_0001",
    handling_lawyer_id: "",
    court_state: "Maharashtra",
    court_district: "Khed",
    court_name: "Additional District Court",
    case_type: "Civil M.A. - Civil Misc. Application",
    filing_number: "2/2026",
    filing_date: "2026-01-02",
    registration_number: "1/2026",
    registration_date: "2026-01-05",
    first_hearing_date: "2026-01-07",
    next_hearing_date: "2026-10-12",
    current_case_stage: "Awaiting Notice",
    presiding_judge: "DISTRICT JUDGE - 1 AND ADDL. SESSIONS JUDGE, KHED",
    petitioner_name: "Vaibhav Bacche",
    petitioner_advocate: "ANDHALE NILESH BALASAHEB",
    respondents_list: ["The State of Maharashtra"],
    applied_act: "",
    applied_section: "",
    case_status: "Case pending",
    calculated_metrics: {
      respondent_count: 1,
      total_case_age_days: 269,
      total_hearings_scheduled: 2,
      current_stage_duration_days: 12,
    },
    case_history_timeline: [
      {
        judge_title: "DISTRICT JUDGE - 1",
        business_on_date: "2026-01-07",
        hearing_date: "2026-01-07",
        purpose_of_hearing: "Reply/Say",
      },
      {
        judge_title: "DISTRICT JUDGE - 1",
        business_on_date: "2026-03-30",
        hearing_date: "2026-03-30",
        purpose_of_hearing: "Awaiting R and P",
      },
    ],
    orders: [],
    timeline: [
      {
        date: "2026-01-02",
        event: "Case filed",
        description: "Filing number 2/2026.",
        purpose: "",
        stage: null,
      },
      {
        date: "2026-01-05",
        event: "Case registered",
        description: "Registration number 1/2026.",
        purpose: "",
        stage: null,
      },
      {
        date: "2026-01-07",
        event: "Reply/Say",
        description: "Before DISTRICT JUDGE - 1 AND ADDL. SESSIONS JUDGE, KHED.",
        purpose: "Reply/Say",
        stage: null,
      },
      {
        date: "2026-03-30",
        event: "Awaiting R and P",
        description: "Before DISTRICT JUDGE - 1 AND ADDL. SESSIONS JUDGE, KHED.",
        purpose: "Awaiting R and P",
        stage: null,
      },
      {
        date: "2026-10-12",
        event: "Next hearing",
        description: "Stage: Awaiting Notice.",
        purpose: "",
        stage: "Awaiting Notice",
      },
    ],
    data_source: {
      provider: "development",
      label: "Offline development dataset",
      live_ecourts_data: false,
      disclaimer: "Development dataset: not live eCourts data.",
    },
    ...overrides,
  };

  /* The service never sends a next-hearing event for a case with no
     listing date — least of all a disposed one — so the fixture holds
     the same line the API does rather than leaving a stray row for the
     screen to have to explain away. */
  if (!record.next_hearing_date) {
    record.timeline = (record.timeline ?? []).filter(
      (step) => step.event !== "Next hearing",
    );
  }

  return record;
}
