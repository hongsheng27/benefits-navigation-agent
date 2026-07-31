import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";

import { ELIGIBILITY_QUESTIONS } from "../../mocks/eligibilityQuestions";
import {
  DIM_MATCHERS,
  FOLLOW_UPS,
  OPENING_MESSAGE,
} from "../../mocks/navigatorChatData";
import {
  MY_DATA_SOURCE_SETS,
  MYDATA_MOCK_VALUES,
  createInitialProfile,
} from "../../mocks/profileData";
import type {
  ChatMessage,
  DetectedDim,
  DimKey,
  MyDataAuthorization,
  NavigatorStep,
  ProfileField,
  ProfileSectionKey,
  ProfileState,
} from "../../types/navigator";

const TURN_GOAL = 3;
const AI_REPLY_DELAY_MS = 450;

type PendingAiTurn = {
  message: ChatMessage;
  dims: DetectedDim[];
  answeredNeeds: DimKey[];
  summaryShown: boolean;
  followUpNeed: DimKey | null;
};

type NavigatorState = {
  step: NavigatorStep;
  returnStepBeforeProfile: NavigatorStep;
  messages: ChatMessage[];
  turn: number;
  turnGoal: number;
  detectedDims: DetectedDim[];
  answeredNeeds: DimKey[];
  currentFollowUpNeed: DimKey | null;
  summaryShown: boolean;
  confirmed: boolean;
  isTyping: boolean;
  pendingAiTurn: PendingAiTurn | null;
  answers: Record<string, string>;
  profile: ProfileState;
  mydata: MyDataAuthorization;
  selectedItemId: string | null;
  showIneligible: boolean;
  explained: boolean;
  toast: string | null;
};

type NavigatorAction =
  | { type: "SEND_USER_MESSAGE"; text: string }
  | { type: "REVEAL_AI_REPLY" }
  | { type: "CONFIRM" }
  | { type: "REVISE" }
  | { type: "GO_TO_MATCH" }
  | { type: "ANSWER_QUESTION"; code: string; value: string }
  | { type: "SKIP_QUESTION"; code: string }
  | { type: "UNDO_LAST_ANSWER" }
  | { type: "RESET_ANSWERS" }
  | { type: "AUTHORIZE_MYDATA" }
  | { type: "REVOKE_MYDATA" }
  | { type: "OPEN_DETAIL"; id: string }
  | { type: "BACK_TO_MATCH" }
  | { type: "OPEN_PROFILE" }
  | { type: "CLOSE_PROFILE" }
  | { type: "EDIT_PROFILE_FIELD"; code: string; value: string }
  | { type: "RESET_ALL_DATA" }
  | { type: "TOGGLE_SHOW_INELIGIBLE" }
  | { type: "REVEAL_PLAIN_EXPLANATION" }
  | { type: "SHOW_TOAST"; message: string }
  | { type: "CLEAR_TOAST" }
  | { type: "GO_TO_STEP"; step: NavigatorStep };

let messageIdCounter = 0;
function nextMessageId(prefix: string) {
  messageIdCounter += 1;
  return `${prefix}-${messageIdCounter}`;
}

function detectDims(text: string): DetectedDim[] {
  return DIM_MATCHERS.filter((matcher) =>
    matcher.keywords.some((keyword) => text.includes(keyword)),
  ).map((matcher) => ({ key: matcher.key, tag: matcher.tag }));
}

function mergeDims(
  existing: DetectedDim[],
  found: DetectedDim[],
): DetectedDim[] {
  const merged = [...existing];
  found.forEach((dim) => {
    if (!merged.some((d) => d.key === dim.key)) {
      merged.push(dim);
    }
  });
  return merged;
}

function markAnswered(existing: DimKey[], need: DimKey | null): DimKey[] {
  if (!need || existing.includes(need)) {
    return existing;
  }
  return [...existing, need];
}

function buildSummaryText(dims: DetectedDim[]): string {
  if (!dims.length) {
    return "謝謝你告訴我這麼多。目前我還沒有抓到明確的情境關鍵字，但沒關係，我們可以先進到下一步，之後隨時可以補充。這樣的理解對嗎？";
  }
  const tags = dims.map((dim) => dim.tag).join("、");
  return `謝謝你告訴我這麼多。目前我理解到的情況包含：${tags}。這樣的理解對嗎？如果有不準確的地方，也可以直接跟我說。`;
}

function planNextAiTurn(
  text: string,
  state: NavigatorState,
): {
  dims: DetectedDim[];
  answeredNeeds: DimKey[];
  nextTurn: number;
  pending: PendingAiTurn;
} {
  const dims = mergeDims(state.detectedDims, detectDims(text));
  const answeredNeeds = markAnswered(
    state.answeredNeeds,
    state.currentFollowUpNeed,
  );
  const nextTurn = state.turn + 1;
  const followUp =
    nextTurn < state.turnGoal
      ? FOLLOW_UPS.find(
          (f) =>
            !answeredNeeds.includes(f.need) &&
            !dims.some((dim) => dim.key === f.need),
        ) ?? null
      : null;

  if (followUp) {
    return {
      dims,
      answeredNeeds,
      nextTurn,
      pending: {
        message: {
          id: nextMessageId("ai"),
          role: "ai",
          text: followUp.ask,
          chips: followUp.chips,
        },
        dims,
        answeredNeeds,
        summaryShown: false,
        followUpNeed: followUp.need,
      },
    };
  }

  return {
    dims,
    answeredNeeds,
    nextTurn,
    pending: {
      message: {
        id: nextMessageId("ai"),
        role: "ai",
        text: buildSummaryText(dims),
      },
      dims,
      answeredNeeds,
      summaryShown: true,
      followUpNeed: null,
    },
  };
}

export function findProfileField(
  profile: ProfileState,
  code: string,
): ProfileField | undefined {
  for (const key of Object.keys(profile) as ProfileSectionKey[]) {
    const field = profile[key].fields.find((f) => f.code === code);
    if (field) {
      return field;
    }
  }
  return undefined;
}

function updateProfileField(
  profile: ProfileState,
  code: string,
  updater: (field: ProfileField) => ProfileField,
): ProfileState {
  const next = { ...profile };
  (Object.keys(next) as ProfileSectionKey[]).forEach((key) => {
    const section = next[key];
    if (section.fields.some((f) => f.code === code)) {
      next[key] = {
        ...section,
        fields: section.fields.map((f) => (f.code === code ? updater(f) : f)),
      };
    }
  });
  return next;
}

function initialState(): NavigatorState {
  return {
    step: "chat",
    returnStepBeforeProfile: "chat",
    messages: [{ id: nextMessageId("ai"), role: "ai", text: OPENING_MESSAGE }],
    turn: 0,
    turnGoal: TURN_GOAL,
    detectedDims: [],
    answeredNeeds: [],
    currentFollowUpNeed: null,
    summaryShown: false,
    confirmed: false,
    isTyping: false,
    pendingAiTurn: null,
    answers: {},
    profile: createInitialProfile(),
    mydata: { authorized: false, authorizedAt: null, expiresAt: null },
    selectedItemId: null,
    showIneligible: false,
    explained: false,
    toast: null,
  };
}

function reducer(
  state: NavigatorState,
  action: NavigatorAction,
): NavigatorState {
  switch (action.type) {
    case "SEND_USER_MESSAGE": {
      const trimmed = action.text.trim();
      if (!trimmed || state.isTyping) {
        return state;
      }
      const userMessage: ChatMessage = {
        id: nextMessageId("user"),
        role: "user",
        text: trimmed,
      };
      const { pending } = planNextAiTurn(trimmed, state);
      return {
        ...state,
        messages: [...state.messages, userMessage],
        isTyping: true,
        pendingAiTurn: pending,
      };
    }
    case "REVEAL_AI_REPLY": {
      if (!state.pendingAiTurn) {
        return state;
      }
      const { message, dims, answeredNeeds, summaryShown, followUpNeed } =
        state.pendingAiTurn;
      return {
        ...state,
        messages: [...state.messages, message],
        detectedDims: dims,
        answeredNeeds,
        currentFollowUpNeed: followUpNeed,
        turn: state.turn + 1,
        summaryShown,
        isTyping: false,
        pendingAiTurn: null,
      };
    }
    case "CONFIRM": {
      if (!state.summaryShown) {
        return state;
      }
      let profile = state.profile;
      if (state.detectedDims.some((dim) => dim.key === "jobless")) {
        const current = findProfileField(profile, "employment")?.value;
        if (!current) {
          profile = updateProfileField(profile, "employment", (f) => ({
            ...f,
            value: "非自願離職",
          }));
        }
      }
      return { ...state, confirmed: true, step: "interpret", profile };
    }
    case "REVISE": {
      if (!state.summaryShown) {
        return state;
      }
      return {
        ...state,
        step: "chat",
        summaryShown: false,
        confirmed: false,
        currentFollowUpNeed: null,
        turnGoal: state.turnGoal + 1,
        messages: [
          ...state.messages,
          {
            id: nextMessageId("ai"),
            role: "ai",
            text: "好的，那我們再多聊一點，還有什麼想補充的嗎？",
          },
        ],
      };
    }
    case "GO_TO_MATCH": {
      return { ...state, step: "match" };
    }
    case "ANSWER_QUESTION": {
      const question = ELIGIBILITY_QUESTIONS.find(
        (q) => q.code === action.code,
      );
      let profile = state.profile;
      if (question?.profileField) {
        profile = updateProfileField(profile, question.profileField, (f) => ({
          ...f,
          value: action.value,
          source: f.source === "mydata" ? "self" : f.source,
        }));
      }
      return {
        ...state,
        answers: { ...state.answers, [action.code]: action.value },
        profile,
      };
    }
    case "SKIP_QUESTION": {
      return {
        ...state,
        answers: { ...state.answers, [action.code]: "不確定" },
      };
    }
    case "UNDO_LAST_ANSWER": {
      const keys = Object.keys(state.answers);
      if (!keys.length) {
        return state;
      }
      const nextAnswers = { ...state.answers };
      delete nextAnswers[keys[keys.length - 1]];
      return { ...state, answers: nextAnswers };
    }
    case "RESET_ANSWERS": {
      return { ...state, answers: {} };
    }
    case "AUTHORIZE_MYDATA": {
      let profile = state.profile;
      MY_DATA_SOURCE_SETS.forEach((set) => {
        profile = updateProfileField(profile, set.fieldCode, (f) => {
          // Only claim MyData provenance for fields it actually fills in.
          // A field that already has a self-entered value was never
          // authorized via MyData, so leave it (and its source) untouched —
          // otherwise revoking MyData later would wipe data the user typed
          // themselves.
          if (f.value) {
            return f;
          }
          return {
            ...f,
            source: "mydata",
            value: MYDATA_MOCK_VALUES[set.fieldCode] || "已取得",
          };
        });
      });
      profile = updateProfileField(profile, "avg", (f) => ({
        ...f,
        value: "NT$ 8,667",
      }));
      const nextAnswers = state.answers.insured_years
        ? state.answers
        : { ...state.answers, insured_years: "15 年以上" };
      return {
        ...state,
        profile,
        answers: nextAnswers,
        mydata: {
          authorized: true,
          authorizedAt: "剛剛完成授權",
          expiresAt: "30 天後到期",
        },
      };
    }
    case "REVOKE_MYDATA": {
      let profile = state.profile;
      (Object.keys(profile) as ProfileSectionKey[]).forEach((key) => {
        profile = {
          ...profile,
          [key]: {
            ...profile[key],
            fields: profile[key].fields.map((f) =>
              f.source === "mydata" ? { ...f, value: "", source: "self" } : f,
            ),
          },
        };
      });
      return {
        ...state,
        profile,
        mydata: { authorized: false, authorizedAt: null, expiresAt: null },
      };
    }
    case "OPEN_DETAIL": {
      return { ...state, selectedItemId: action.id, step: "detail" };
    }
    case "BACK_TO_MATCH": {
      return { ...state, step: "match" };
    }
    case "OPEN_PROFILE": {
      if (state.step === "profile") {
        return state;
      }
      return { ...state, returnStepBeforeProfile: state.step, step: "profile" };
    }
    case "CLOSE_PROFILE": {
      return { ...state, step: state.returnStepBeforeProfile };
    }
    case "EDIT_PROFILE_FIELD": {
      const profile = updateProfileField(state.profile, action.code, (f) => ({
        ...f,
        value: action.value,
        source: f.source === "mydata" ? "self" : f.source,
      }));
      return { ...state, profile };
    }
    case "RESET_ALL_DATA": {
      return initialState();
    }
    case "TOGGLE_SHOW_INELIGIBLE": {
      return { ...state, showIneligible: !state.showIneligible };
    }
    case "REVEAL_PLAIN_EXPLANATION": {
      return { ...state, explained: true };
    }
    case "SHOW_TOAST": {
      return { ...state, toast: action.message };
    }
    case "CLEAR_TOAST": {
      return { ...state, toast: null };
    }
    case "GO_TO_STEP": {
      if (action.step === "profile") {
        return state;
      }
      return { ...state, step: action.step };
    }
    default:
      return state;
  }
}

type NavigatorContextValue = {
  state: NavigatorState;
  sendMessage: (text: string) => void;
  confirmUnderstanding: () => void;
  reviseUnderstanding: () => void;
  goToMatch: () => void;
  answerQuestion: (code: string, value: string) => void;
  skipQuestion: (code: string) => void;
  undoLastAnswer: () => void;
  resetAnswers: () => void;
  authorizeMyData: () => void;
  revokeMyData: () => void;
  openDetail: (id: string) => void;
  backToMatch: () => void;
  openProfile: () => void;
  closeProfile: () => void;
  editProfileField: (code: string, value: string) => void;
  resetAllData: () => void;
  toggleShowIneligible: () => void;
  revealPlainExplanation: () => void;
  showToast: (message: string) => void;
  goToStep: (step: NavigatorStep) => void;
};

const NavigatorContext = createContext<NavigatorContextValue | null>(null);

export function NavigatorProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);

  useEffect(() => {
    if (!state.isTyping || !state.pendingAiTurn) {
      return;
    }
    const timer = setTimeout(() => {
      dispatch({ type: "REVEAL_AI_REPLY" });
    }, AI_REPLY_DELAY_MS);
    return () => clearTimeout(timer);
  }, [state.isTyping, state.pendingAiTurn]);

  useEffect(() => {
    if (!state.toast) {
      return;
    }
    const timer = setTimeout(() => {
      dispatch({ type: "CLEAR_TOAST" });
    }, 2500);
    return () => clearTimeout(timer);
  }, [state.toast]);

  const sendMessage = useCallback((text: string) => {
    dispatch({ type: "SEND_USER_MESSAGE", text });
  }, []);
  const confirmUnderstanding = useCallback(() => {
    dispatch({ type: "CONFIRM" });
  }, []);
  const reviseUnderstanding = useCallback(() => {
    dispatch({ type: "REVISE" });
  }, []);
  const goToMatch = useCallback(() => {
    dispatch({ type: "GO_TO_MATCH" });
  }, []);
  const answerQuestion = useCallback((code: string, value: string) => {
    dispatch({ type: "ANSWER_QUESTION", code, value });
  }, []);
  const skipQuestion = useCallback((code: string) => {
    dispatch({ type: "SKIP_QUESTION", code });
  }, []);
  const undoLastAnswer = useCallback(() => {
    dispatch({ type: "UNDO_LAST_ANSWER" });
  }, []);
  const resetAnswers = useCallback(() => {
    dispatch({ type: "RESET_ANSWERS" });
  }, []);
  const authorizeMyData = useCallback(() => {
    dispatch({ type: "AUTHORIZE_MYDATA" });
  }, []);
  const revokeMyData = useCallback(() => {
    dispatch({ type: "REVOKE_MYDATA" });
  }, []);
  const openDetail = useCallback((id: string) => {
    dispatch({ type: "OPEN_DETAIL", id });
  }, []);
  const backToMatch = useCallback(() => {
    dispatch({ type: "BACK_TO_MATCH" });
  }, []);
  const openProfile = useCallback(() => {
    dispatch({ type: "OPEN_PROFILE" });
  }, []);
  const closeProfile = useCallback(() => {
    dispatch({ type: "CLOSE_PROFILE" });
  }, []);
  const editProfileField = useCallback((code: string, value: string) => {
    dispatch({ type: "EDIT_PROFILE_FIELD", code, value });
  }, []);
  const resetAllData = useCallback(() => {
    dispatch({ type: "RESET_ALL_DATA" });
  }, []);
  const toggleShowIneligible = useCallback(() => {
    dispatch({ type: "TOGGLE_SHOW_INELIGIBLE" });
  }, []);
  const revealPlainExplanation = useCallback(() => {
    dispatch({ type: "REVEAL_PLAIN_EXPLANATION" });
  }, []);
  const showToast = useCallback((message: string) => {
    dispatch({ type: "SHOW_TOAST", message });
  }, []);
  const goToStep = useCallback((step: NavigatorStep) => {
    dispatch({ type: "GO_TO_STEP", step });
  }, []);

  const value = useMemo(
    () => ({
      state,
      sendMessage,
      confirmUnderstanding,
      reviseUnderstanding,
      goToMatch,
      answerQuestion,
      skipQuestion,
      undoLastAnswer,
      resetAnswers,
      authorizeMyData,
      revokeMyData,
      openDetail,
      backToMatch,
      openProfile,
      closeProfile,
      editProfileField,
      resetAllData,
      toggleShowIneligible,
      revealPlainExplanation,
      showToast,
      goToStep,
    }),
    [
      state,
      sendMessage,
      confirmUnderstanding,
      reviseUnderstanding,
      goToMatch,
      answerQuestion,
      skipQuestion,
      undoLastAnswer,
      resetAnswers,
      authorizeMyData,
      revokeMyData,
      openDetail,
      backToMatch,
      openProfile,
      closeProfile,
      editProfileField,
      resetAllData,
      toggleShowIneligible,
      revealPlainExplanation,
      showToast,
      goToStep,
    ],
  );

  return (
    <NavigatorContext.Provider value={value}>
      {children}
    </NavigatorContext.Provider>
  );
}

export function useNavigator() {
  const ctx = useContext(NavigatorContext);
  if (!ctx) {
    throw new Error("useNavigator must be used within a NavigatorProvider");
  }
  return ctx;
}
