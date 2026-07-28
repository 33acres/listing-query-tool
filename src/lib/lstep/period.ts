import type { LstepFriend } from "@/types/lstep";

export interface DatePeriod {
  start: Date;
  end: Date;
}

export function filterByPeriod(
  friends: LstepFriend[],
  period?: DatePeriod,
): LstepFriend[] {
  if (!period) return friends;
  return friends.filter(
    (friend) => friend.addedAt >= period.start && friend.addedAt <= period.end,
  );
}
