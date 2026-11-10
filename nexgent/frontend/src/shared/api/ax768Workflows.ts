export const ACTIVE_AX768_WORKFLOW = "device_adjustment_power" as const;
export const AX768_WORKFLOWS = [
  { id: ACTIVE_AX768_WORKFLOW, name: "기기위치조정/전원연결", available: true },
  { id: "information_update", name: "정보확인&수정", available: false },
  { id: "device_collection", name: "기기회수", available: false },
  { id: "device_replacement", name: "기기교체", available: false },
  { id: "device_loss", name: "기기분실", available: false },
  { id: "new_installation", name: "가입자신규설치", available: false }
] as const;
export type Ax768WorkflowId = typeof AX768_WORKFLOWS[number]["id"];
