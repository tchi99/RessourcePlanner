export const SHIFT_DRAG_TYPE = "application/x-resourceplanner-shift";
export const SEGMENT_DRAG_TYPE = "application/x-resourceplanner-segment";

export type ShiftDragPayload = {
  kind: "SHIFT";
  allocation_id: string;
  resource_id: string;
  work_date: string;
};

export type SegmentDragPayload = {
  kind: "SEGMENT";
  segment_id: string;
};

function parse<T>(transfer: DataTransfer, type: string): T | null {
  const raw = transfer.getData(type);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function writeShiftDrag(transfer: DataTransfer, payload: ShiftDragPayload) {
  transfer.effectAllowed = "move";
  transfer.setData(SHIFT_DRAG_TYPE, JSON.stringify(payload));
  transfer.setData("text/plain", payload.allocation_id);
}

export function writeSegmentDrag(transfer: DataTransfer, payload: SegmentDragPayload) {
  transfer.effectAllowed = "move";
  transfer.setData(SEGMENT_DRAG_TYPE, JSON.stringify(payload));
  transfer.setData("text/plain", payload.segment_id);
}

export function hasShiftDrag(transfer: DataTransfer) {
  return Array.from(transfer.types).includes(SHIFT_DRAG_TYPE);
}

export function hasSegmentDrag(transfer: DataTransfer) {
  return Array.from(transfer.types).includes(SEGMENT_DRAG_TYPE);
}

export function readShiftDrag(transfer: DataTransfer): ShiftDragPayload | null {
  const payload = parse<ShiftDragPayload>(transfer, SHIFT_DRAG_TYPE);
  if (!payload || payload.kind !== "SHIFT" || !payload.allocation_id) return null;
  return payload;
}

export function readSegmentDrag(transfer: DataTransfer): SegmentDragPayload | null {
  const payload = parse<SegmentDragPayload>(transfer, SEGMENT_DRAG_TYPE);
  if (!payload || payload.kind !== "SEGMENT" || !payload.segment_id) return null;
  return payload;
}
