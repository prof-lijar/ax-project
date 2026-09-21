import { createContext, useContext } from "react";
import type { Account } from "../../shared/api/accountClient";

export const AccountContext = createContext<Account | null>(null);
export function useAccount() {
  const account = useContext(AccountContext);
  if (!account) throw new Error("Account context requires a signed-in user.");
  return account;
}
