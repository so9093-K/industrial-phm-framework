/** 설비가 하는 일: 관제 카드의 한 줄(short)과 설비·데이터 안내의 설명(role·purpose). */
export type EquipmentRole = {short: string; role: string; purpose: string};
const ROLES: Record<string, EquipmentRole> = {
  "공기압축기": {short: "압축공기 공급", role: "공정에 필요한 압축공기를 공급합니다.", purpose: "전원과 운전 패턴의 변화를 살펴 점검 대상을 찾습니다."},
  "펌프": {short: "액체 이송", role: "액체를 이송해 공정에 공급합니다.", purpose: "전압·전류 변화를 살펴 운전 상태가 달라진 구간을 찾습니다."},
  "보일러": {short: "열 공급", role: "공정이나 난방에 필요한 열을 공급합니다.", purpose: "전원과 소비 전류의 변화를 살펴 운전 패턴을 확인합니다."},
  "베어링": {short: "회전축 지지", role: "모터·펌프·팬의 회전축을 지지하는 부품입니다.", purpose: "진동 크기와 충격 성분의 변화를 살펴 점검·교체 계획에 활용합니다."},
};
/** 데이터셋 종류와 설비 이름으로 찾는다. 베어링 시험 기록은 설비 이름 대신 시험 조건이 붙어 있다. */
export function equipmentRole(kind: string | null | undefined, equipment: string | null | undefined): EquipmentRole | null {
  if (kind === "xjtu-sy") return ROLES["베어링"];
  return equipment ? ROLES[equipment] ?? null : null;
}
