import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RegisterPage from "./RegisterPage";
import {
  register,
  registerLawyerAccount,
  uploadLawyerDocument,
} from "../../api/authApi";
import type { Session } from "../../auth/session";

/* =========================================================
   REGISTER PAGE — the states the screen can be in.

   The auth API is mocked, so what is under test is this
   component's own behaviour: the account-type choice, which
   fields exist (and which dangerous one does NOT), what it
   refuses to send, how it surfaces the server's answer, and
   the lawyer submission flow (register + document upload +
   the pending confirmation). The real endpoints are covered
   by NyayMitra-feature-lawyer-api/tests.
   ========================================================= */

vi.mock("../../api/authApi", () => ({
  register: vi.fn(),
  registerLawyerAccount: vi.fn(),
  uploadLawyerDocument: vi.fn(),
}));

const mockedRegister = vi.mocked(register);
const mockedRegisterLawyer = vi.mocked(registerLawyerAccount);
const mockedUpload = vi.mocked(uploadLawyerDocument);

afterEach(() => {
  /* Vitest runs without globals here, so Testing Library cannot hook
     its own cleanup — unmount by hand, or the next test finds two
     of every element on the page. */
  cleanup();
  vi.clearAllMocks();
});

const NEW_SESSION: Session = {
  userId: "5",
  fullName: "New Citizen",
  email: "new@example.com",
  role: "USER",
  token: "test-token",
  loginAt: "2026-10-02T00:00:00.000Z",
};

const LAWYER_SESSION: Session = {
  userId: "9",
  fullName: "Test Advocate",
  email: "advocate@example.com",
  role: "LAWYER",
  token: "lawyer-token",
  loginAt: "2026-10-02T00:00:00.000Z",
  lawyerId: "LAWYER_0007",
  verificationStatus: "PENDING",
};

interface FormValues {
  fullName: string;
  email: string;
  password: string;
  confirmation: string;
}

const VALID: FormValues = {
  fullName: "New Citizen",
  email: "new@example.com",
  password: "password123",
  confirmation: "password123",
};

function openUserForm(): void {
  fireEvent.click(
    screen.getByRole("button", { name: /create user account/i }),
  );
}

function openLawyerForm(): void {
  fireEvent.click(
    screen.getByRole("button", { name: /create lawyer account/i }),
  );
}

function fill(values: FormValues): void {
  fireEvent.change(screen.getByPlaceholderText("e.g. Asha Verma"), {
    target: { value: values.fullName },
  });
  fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
    target: { value: values.email },
  });
  fireEvent.change(
    screen.getByPlaceholderText("At least 8 characters"),
    { target: { value: values.password } },
  );
  fireEvent.change(
    screen.getByPlaceholderText("Repeat the password"),
    { target: { value: values.confirmation } },
  );
}

function submit(): void {
  /*
   * Submit the form directly rather than clicking the button: jsdom
   * enforces native `type="email"` validation on a button-triggered
   * submission, which would silently swallow the submit for an
   * invalid address before the component's own message could show.
   * (A real browser shows its native hint in that case instead —
   * the component's regex still guards everything else.)
   */
  fireEvent.submit(
    document.querySelector(".login-form") as HTMLFormElement,
  );
}

function fillLawyer(
  extra: Record<string, string> = {},
): void {
  fireEvent.change(
    screen.getByPlaceholderText("e.g. Adv. Priya Sharma"),
    { target: { value: "Test Advocate" } },
  );
  fireEvent.change(
    screen.getByPlaceholderText("advocate@example.com"),
    { target: { value: "advocate@example.com" } },
  );
  fireEvent.change(
    screen.getByPlaceholderText("At least 8 characters"),
    { target: { value: "password123" } },
  );
  fireEvent.change(
    screen.getByPlaceholderText("Repeat the password"),
    { target: { value: "password123" } },
  );
  fireEvent.change(
    screen.getByPlaceholderText("e.g. MAH/1234/2020"),
    { target: { value: "MAH/1234/2020" } },
  );
  fireEvent.change(
    screen.getByPlaceholderText("e.g. Criminal Law, Family Law"),
    { target: { value: "Criminal Law, Family Law" } },
  );

  for (const [placeholder, value] of Object.entries(extra)) {
    fireEvent.change(screen.getByPlaceholderText(placeholder), {
      target: { value },
    });
  }
}

function attachDocument(
  name = "licence.pdf",
  content = "%PDF-1.4 fake bytes",
  type = "application/pdf",
): File {
  const input = document.querySelector(
    'input[type="file"]',
  ) as HTMLInputElement;

  const file = new File([content], name, { type });

  fireEvent.change(input, { target: { files: [file] } });

  return file;
}

/* =========================================================
   ACCOUNT-TYPE CHOICE
   ========================================================= */

describe("account-type choice", () => {
  it("offers a user account or a lawyer account — nothing else", () => {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: /create user account/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /create lawyer account/i }),
    ).toBeInTheDocument();

    /* No admin path of any kind. */
    expect(
      screen.queryByRole("button", { name: /admin/i }),
    ).toBeNull();
    expect(
      screen.queryByText(/administrator/i),
    ).toBeNull();
  });

  it("shows no form until a type is picked", () => {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    expect(
      screen.queryByPlaceholderText("e.g. Asha Verma"),
    ).toBeNull();
    expect(
      screen.queryByPlaceholderText("e.g. MAH/1234/2020"),
    ).toBeNull();
  });

  it("goes back to sign-in from the choice screen", () => {
    const onBack = vi.fn();

    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={onBack}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /back to sign in/i }),
    );

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(mockedRegister).not.toHaveBeenCalled();
    expect(mockedRegisterLawyer).not.toHaveBeenCalled();
  });
});

/* =========================================================
   CITIZEN FORM — FIELDS
   ========================================================= */

describe("fields", () => {
  it("asks for name, email and the password twice", () => {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    openUserForm();

    expect(
      screen.getByPlaceholderText("e.g. Asha Verma"),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("you@example.com"),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("At least 8 characters"),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("Repeat the password"),
    ).toBeInTheDocument();
  });

  it("offers no role picker at all — no selects, no radios", () => {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    openUserForm();

    expect(document.querySelector("select")).toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByText(/administrator/i)).toBeNull();
  });

  it("returns to the choice screen, and to sign-in from there", () => {
    const onBack = vi.fn();

    render(
      <RegisterPage onAuthenticated={vi.fn()} onBack={onBack} />,
    );

    openUserForm();

    fireEvent.click(
      screen.getByRole("button", { name: /choose account type/i }),
    );

    expect(
      screen.getByRole("button", { name: /create user account/i }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /already have an account/i }),
    );

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(mockedRegister).not.toHaveBeenCalled();
  });
});

/* =========================================================
   CITIZEN FORM — CLIENT-SIDE VALIDATION
   ========================================================= */

describe("client-side validation", () => {
  it("refuses mismatched passwords with a message, not a request", () => {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    openUserForm();
    fill({ ...VALID, confirmation: "different123" });
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Passwords do not match.",
    );
    expect(mockedRegister).not.toHaveBeenCalled();
  });

  it("refuses a short password", () => {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    openUserForm();
    fill({ ...VALID, password: "short", confirmation: "short" });
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "at least 8 characters",
    );
    expect(mockedRegister).not.toHaveBeenCalled();
  });

  it("refuses a malformed email", () => {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    openUserForm();
    fill({ ...VALID, email: "not-an-email" });
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a valid email address.",
    );
    expect(mockedRegister).not.toHaveBeenCalled();
  });

  it("refuses an empty name", () => {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    openUserForm();
    fill({ ...VALID, fullName: "   " });
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter your full name.",
    );
    expect(mockedRegister).not.toHaveBeenCalled();
  });
});

/* =========================================================
   CITIZEN FORM — SUCCESS + SERVER ERRORS
   ========================================================= */

describe("successful registration", () => {
  it("sends the four fields (no role) and hands over the session", async () => {
    mockedRegister.mockResolvedValue(NEW_SESSION);

    const onAuthenticated = vi.fn();

    render(
      <RegisterPage
        onAuthenticated={onAuthenticated}
        onBack={vi.fn()}
      />,
    );

    openUserForm();
    fill(VALID);
    submit();

    expect(mockedRegister).toHaveBeenCalledWith({
      fullName: VALID.fullName,
      email: VALID.email,
      password: VALID.password,
      passwordConfirmation: VALID.confirmation,
    });
    expect(mockedRegister).not.toHaveBeenCalledWith(
      expect.objectContaining({ role: expect.anything() }),
    );

    await waitFor(() =>
      expect(onAuthenticated).toHaveBeenCalledWith(NEW_SESSION),
    );
  });
});

describe("server errors", () => {
  it("shows the backend's message (duplicate email)", async () => {
    mockedRegister.mockRejectedValue(
      new Error("An account with this email already exists."),
    );

    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    openUserForm();
    fill(VALID);
    submit();

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent("An account with this email already exists.");
  });
});

/* =========================================================
   LAWYER FORM — FIELDS
   ========================================================= */

describe("lawyer form", () => {
  it("asks for the licence, practice areas and the document", () => {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    openLawyerForm();

    expect(
      screen.getByPlaceholderText("e.g. Adv. Priya Sharma"),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("e.g. MAH/1234/2020"),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("e.g. Criminal Law, Family Law"),
    ).toBeInTheDocument();
    expect(
      document.querySelector('input[type="file"]'),
    ).not.toBeNull();

    /* The optional profile details. */
    expect(
      screen.getByPlaceholderText("e.g. Bar Council of Maharashtra"),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("+91 98765 43210"),
    ).toBeInTheDocument();

    /* Still no role picker anywhere. */
    expect(document.querySelector("select")).toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByText(/administrator/i)).toBeNull();
  });
});

/* =========================================================
   LAWYER FORM — VALIDATION (nothing sent, nothing uploaded)
   ========================================================= */

describe("lawyer validation", () => {
  function renderLawyer() {
    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );
    openLawyerForm();
  }

  it("refuses a missing licence number", () => {
    renderLawyer();
    fillLawyer({ "e.g. MAH/1234/2020": "   " });
    attachDocument();
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter your licence or registration number.",
    );
    expect(mockedRegisterLawyer).not.toHaveBeenCalled();
    expect(mockedUpload).not.toHaveBeenCalled();
  });

  it("refuses empty practice areas", () => {
    renderLawyer();
    fillLawyer({ "e.g. Criminal Law, Family Law": " , " });
    attachDocument();
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "List at least one practice area.",
    );
    expect(mockedRegisterLawyer).not.toHaveBeenCalled();
  });

  it("refuses a missing document", () => {
    renderLawyer();
    fillLawyer();
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Attach your licence or registration document",
    );
    expect(mockedRegisterLawyer).not.toHaveBeenCalled();
    expect(mockedUpload).not.toHaveBeenCalled();
  });

  it("refuses a file that is not a PDF, JPG or PNG", () => {
    renderLawyer();
    fillLawyer();
    attachDocument("form.html", "<html></html>", "text/html");
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Upload a PDF, JPG or PNG file.",
    );
    expect(mockedRegisterLawyer).not.toHaveBeenCalled();
    expect(mockedUpload).not.toHaveBeenCalled();
  });

  it("refuses an oversized document", () => {
    renderLawyer();
    fillLawyer();

    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const big = new File(
      [new ArrayBuffer(10 * 1024 * 1024 + 1)],
      "licence.pdf",
      { type: "application/pdf" },
    );
    fireEvent.change(input, { target: { files: [big] } });

    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "File too large. Maximum allowed size is 10 MB.",
    );
    expect(mockedUpload).not.toHaveBeenCalled();
  });

  it("refuses out-of-range experience", () => {
    renderLawyer();
    fillLawyer({ "e.g. 7": "99" });
    attachDocument();
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Years of experience must be between 0 and 70.",
    );
    expect(mockedRegisterLawyer).not.toHaveBeenCalled();
  });
});

/* =========================================================
   LAWYER FORM — SUBMISSION
   ========================================================= */

describe("lawyer submission", () => {
  it("registers, uploads the document, and shows the pending screen", async () => {
    mockedRegisterLawyer.mockResolvedValue(LAWYER_SESSION);
    mockedUpload.mockResolvedValue(undefined);

    const onAuthenticated = vi.fn();

    render(
      <RegisterPage
        onAuthenticated={onAuthenticated}
        onBack={vi.fn()}
      />,
    );

    openLawyerForm();
    fillLawyer();
    attachDocument();
    submit();

    await waitFor(() =>
      expect(mockedUpload).toHaveBeenCalledWith(
        "lawyer-token",
        expect.objectContaining({ name: "licence.pdf" }),
      ),
    );

    /* The message the brief requires, verbatim. */
    expect(
      await screen.findByText(
        /Your lawyer registration is pending\s+admin verification\./,
      ),
    ).toBeInTheDocument();

    /* Registration is server-side PENDING; the page never signs
       the lawyer into the dashboard by itself. */
    expect(onAuthenticated).not.toHaveBeenCalled();
    expect(mockedRegister).not.toHaveBeenCalled();
  });

  it("keeps the created account when the upload fails, and retries only the upload", async () => {
    mockedRegisterLawyer.mockResolvedValue(LAWYER_SESSION);
    mockedUpload
      .mockRejectedValueOnce(
        new Error("File too large. Maximum allowed size is 10 MB."),
      )
      .mockResolvedValue(undefined);

    const onAuthenticated = vi.fn();

    render(
      <RegisterPage
        onAuthenticated={onAuthenticated}
        onBack={vi.fn()}
      />,
    );

    openLawyerForm();
    fillLawyer();
    attachDocument();
    submit();

    /* First attempt: the account exists, the upload failed. */
    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent(
      "File too large. Maximum allowed size is 10 MB.",
    );

    expect(
      screen.getByText(/Your account was created/i),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: /retry document upload/i,
      }),
    ).toBeInTheDocument();

    expect(mockedRegisterLawyer).toHaveBeenCalledTimes(1);

    /* Second attempt: registration is NOT run again. */
    fireEvent.submit(
      document.querySelector(".login-form") as HTMLFormElement,
    );

    expect(
      await screen.findByText(
        /Your lawyer registration is pending\s+admin verification\./,
      ),
    ).toBeInTheDocument();

    expect(mockedRegisterLawyer).toHaveBeenCalledTimes(1);
    expect(mockedUpload).toHaveBeenCalledTimes(2);
    expect(onAuthenticated).not.toHaveBeenCalled();
  });

  it("surfaces a registration failure without touching the upload", async () => {
    mockedRegisterLawyer.mockRejectedValue(
      new Error("An account with this email already exists."),
    );

    render(
      <RegisterPage
        onAuthenticated={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    openLawyerForm();
    fillLawyer();
    attachDocument();
    submit();

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent(
      "An account with this email already exists.",
    );
    expect(mockedUpload).not.toHaveBeenCalled();
  });
});
