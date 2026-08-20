export type RequestLane = "chat" | "weekly-report";

export class RequestLanes {
  private readonly controllers = new Map<RequestLane, AbortController>();

  start(lane: RequestLane): AbortController | null {
    if (this.controllers.has(lane)) {
      return null;
    }
    const controller = new AbortController();
    this.controllers.set(lane, controller);
    return controller;
  }

  finish(lane: RequestLane, controller: AbortController): void {
    if (this.controllers.get(lane) === controller) {
      this.controllers.delete(lane);
    }
  }

  cancel(lane: RequestLane): void {
    this.controllers.get(lane)?.abort();
  }

  cancelAll(): void {
    for (const controller of this.controllers.values()) {
      controller.abort();
    }
    this.controllers.clear();
  }
}
