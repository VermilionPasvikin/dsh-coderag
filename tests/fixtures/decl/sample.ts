import { x } from "./x";

export function add(a: number, b: number): number {
  return a + b;
}

export class Pool {
  acquire(): number {
    return 1;
  }
}

const arrow = (a: number): number => a;
