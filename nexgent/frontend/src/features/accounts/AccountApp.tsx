import { LanguageSelect } from "../../shared/i18n/LanguageSelect";
import { t, useLanguage } from "../../shared/i18n";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AccountError, accountClient, type Account, type AccessCatalog, type AccessKind, type AccessUser } from "../../shared/api/accountClient";
import styles from "./AccountApp.module.css";
import { useAccount } from "./accountContext";
import { AUTH_EXPIRED_EVENT } from "../../shared/api/authenticatedFetch";
import { validatePasswordConfirmation, clearPasswordConfirmationError } from "./passwordConfirmation";

type Section = "users" | AccessKind;
type Act = (operation: () => Promise<void>) => Promise<boolean>;
const message = (error: unknown) => error instanceof Error ? error.message : t("The request failed. Please try again.");

export function SignIn({ onSignedIn }: { onSignedIn: () => Promise<unknown> }) {
  useLanguage((state) => state.language);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    form.reset();
    setBusy(true); setError("");
    try { await accountClient.login(String(data.get("username")), String(data.get("password"))); await onSignedIn(); }
    catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }
  return <main className={styles.login}><div className={styles.loginBody}>
    <span className={styles.brand}>Nexgent</span>
    <LanguageSelect />
    <h1>{t("Sign in")}</h1><p>{t("Use the account created by your administrator.")}</p>
    <form onSubmit={event => void submit(event)} className={styles.form}>
      <label>{t("Username")}<input name="username" autoComplete="username" required maxLength={64} autoFocus /></label>
      <label>{t("Password")}<input name="password" type="password" autoComplete="current-password" required maxLength={256} /></label>
      {error && <p role="alert" className={styles.error}>{t(error)}</p>}
      <button type="submit" disabled={busy}>{busy ? t("Signing in…") : t("Sign in")}</button>
    </form>
    <p className={styles.hint}>{t("Need an account or a password reset? Contact your administrator.")}</p>
  </div></main>;
}

export function AccountSettings() {
  useLanguage((state) => state.language);
  const account = useAccount();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const act: Act = async operation => {
    setBusy(true); setError(""); setNotice("");
    try {
      await operation();
      await client.invalidateQueries({ queryKey: ["account"] });
      await client.invalidateQueries({ queryKey: ["access"] });
      setNotice("Saved."); return true;
    } catch (cause) {
      setError(message(cause));
      if (cause instanceof AccountError && [401, 403].includes(cause.status)) {
        client.removeQueries({ queryKey: ["access"] });
        await client.invalidateQueries({ queryKey: ["account"] });
      }
      return false;
    } finally { setBusy(false); }
  };
  return <section className={styles.page}>
    <header className={styles.header}><span>{account.name}</span>
      <button disabled={busy} onClick={() => void act(async () => {
        await accountClient.logout(account.csrf_token);
        await client.cancelQueries();
        client.removeQueries({ queryKey: ["access"] });
        client.setQueryData(["account"], null);
        window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
      })}><LogOut size={16} aria-hidden /> {t("Sign out all devices")}</button></header>
    <div className={styles.content}>
      <h1>{t("Settings")}</h1>
      <section className={styles.profile} aria-labelledby="account-profile-title">
        <h2 id="account-profile-title">{t("Signed-in account")}</h2>
        <dl className={styles.profileDetails}>
          <div><dt>{t("Name")}</dt><dd>{account.name || account.username}</dd></div>
          <div><dt>{t("Username")}</dt><dd>{account.username}</dd></div>
          <div><dt>{t("Email")}</dt><dd>{account.email || t("Not provided")}</dd></div>
          <div><dt>{t("Account type")}</dt><dd>{account.is_admin ? t("Administrator") : t("Member")}</dd></div>
          <div><dt>{t("Roles")}</dt><dd>{account.roles.join(", ") || t("No roles assigned")}</dd></div>
        </dl>
      </section>
      <LanguageSelect />
      {error && <p role="alert" className={styles.error}>{t(error)}</p>}
      {notice && <p role="status">{t(notice)}</p>}
      {account.is_admin ? <>
        <h2>{t("Manage access")}</h2>
        <AccessAdmin account={account} busy={busy} act={act} />
      </> : <section>
        <p>{t("You’re signed in. Contact your administrator for account or access changes.")}</p>
        <p>{t("Permissions:")} {account.permissions.join(", ") || t("None assigned")}</p>
      </section>}
    </div>
  </section>;
}
function Checks({ title, name, options, selected = [] }: {
  title: string; name: string; options: { id: string; label: string }[]; selected?: string[];
}) {
  useLanguage((state) => state.language);
  return <fieldset className={styles.choices}><legend>{title}</legend>
    {options.length === 0 && <p className={styles.hint}>{t("None available yet.")}</p>}
    {options.map(option => <label key={option.id}><input type="checkbox" name={name} value={option.id}
      defaultChecked={selected.includes(option.id)} />{option.label}</label>)}
  </fieldset>;
}
function PasswordInput() {
  useLanguage((state) => state.language);
  return <label>{t("Password (4–12 characters)")}<input name="password" type="password" autoComplete="new-password"
    minLength={4} maxLength={12} required /></label>;
}
function AccessAdmin({ account, busy, act }: { account: Account; busy: boolean; act: Act }) {
  useLanguage((state) => state.language);
  const [section, setSection] = useState<Section>("users");
  const [editing, setEditing] = useState<string | null | undefined>(undefined);
  const [resetUser, setResetUser] = useState<AccessUser | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const query = useQuery({ queryKey: ["access", account.id], queryFn: ({ signal }) => accountClient.catalog(signal),
    retry: false, refetchOnWindowFocus: true });
  if (query.isPending) return <p role="status">{t("Loading access…")}</p>;
  if (query.isError) return <p role="alert">{t("Access settings could not be loaded.")} <button onClick={() => void query.refetch()}>{t("Try again")}</button></p>;
  const data = query.data;
  return <>
    <nav className={styles.tabs} aria-label={t("Access management")}>{(["users", "groups", "roles", "permissions"] as const).map(kind =>
      <button key={kind} aria-current={kind === section ? "page" : undefined} disabled={busy} onClick={() => {
        setSection(kind); setEditing(undefined); setResetUser(null); setDeleting(null);
      }}>{t(kind[0].toUpperCase() + kind.slice(1))}</button>)}</nav>
    <div className={styles.toolbar}><h2>{t(section[0].toUpperCase() + section.slice(1))}</h2>
      <button disabled={busy} onClick={() => { setEditing(null); setResetUser(null); }}>{t("Create " + (section === "users" ? "account" : section.slice(0, -1)))}</button></div>
    {section === "permissions" && <p className={styles.hint}>{t("Permission keys are assigned through roles. Each feature must enforce its supported keys.")}</p>}
    {editing !== undefined && <AccessEditor key={section + (editing ?? "new")} section={section} id={editing} data={data}
      csrf={account.csrf_token} busy={busy} act={act} close={() => setEditing(undefined)} />}
    {resetUser && <form key={resetUser.id} className={styles.editor}
      onInput={event => clearPasswordConfirmationError(event.currentTarget)} onSubmit={event => {
      event.preventDefault();
      if (busy) return;
      const form = event.currentTarget;
      if (!validatePasswordConfirmation(form)) return;
      const values = new FormData(form); form.reset();
      void act(() => accountClient.resetPassword(resetUser.id, String(values.get("password")), account.csrf_token)).then(ok => { if (ok) setResetUser(null); });
    }}><h3>{t("Reset password for")} {resetUser.username}</h3><p>{t("This signs the account out on all devices.")}</p>
      <fieldset disabled={busy} className={styles.fields}>
        <PasswordInput />
        <label>{t("Confirm password")}<input name="confirm_password" type="password" autoComplete="new-password"
          minLength={4} maxLength={12} required /></label>
      </fieldset>
      <div className={styles.actions}><button disabled={busy}>{t("Save password")}</button>
        <button type="button" disabled={busy} onClick={() => setResetUser(null)}>{t("Cancel")}</button></div></form>}
    <ul className={styles.list}>{data[section].map(item => {
      const user = section === "users" ? item as AccessUser : null;
      const label = "username" in item ? item.username : "key" in item ? item.key : item.name;
      const system = "is_system" in item && item.is_system;
      return <li key={item.id}><div className={styles.details}><strong>{label}</strong>
        <small>{user ? `${user.name} · ${user.is_active ? t("Active") : t("Disabled")}${user.password_set ? "" : t(" · Password needed")}` : "description" in item ? item.description : ""}</small>
        {user && <small>{t("Effective permissions:")} {user.permissions.join(", ") || t("None")}</small>}
        {system && <small><ShieldCheck size={13} aria-hidden /> {t("Built-in")}</small>}</div>
        <div className={styles.actions}>{!system && <button disabled={busy} onClick={() => { setEditing(item.id); setResetUser(null); }}>{t("Edit")} <span className={styles.srOnly}>{label}</span></button>}
          {user ? <button disabled={busy} onClick={() => { setResetUser(user); setEditing(undefined); }}>{t("Reset password")} <span className={styles.srOnly}>{label}</span></button>
            : !system && (deleting === item.id ? <><span>{t("Remove assignments too?")}</span>
              <button disabled={busy} onClick={() => void act(() => accountClient.remove(section as AccessKind, item.id, account.csrf_token)).then(ok => { if (ok) setDeleting(null); })}>{t("Confirm delete")}</button>
              <button disabled={busy} onClick={() => setDeleting(null)}>{t("Cancel")}</button></>
              : <button disabled={busy} onClick={() => setDeleting(item.id)}>{t("Delete")} <span className={styles.srOnly}>{label}</span></button>)}</div>
      </li>;
    })}</ul>
    {data[section].length === 0 && <p>{t(`No ${section} yet.`)}</p>}
  </>;
}
function AccessEditor({ section, id, data, csrf, busy, act, close }: {
  section: Section; id: string | null; data: AccessCatalog; csrf: string; busy: boolean; act: Act; close: () => void;
}) {
  useLanguage((state) => state.language);
  const item = data[section].find(entry => entry.id === id);
  const user = section === "users" ? item as AccessUser | undefined : undefined;
  const group = section === "groups" ? data.groups.find(entry => entry.id === id) : undefined;
  const role = section === "roles" ? data.roles.find(entry => entry.id === id) : undefined;
  const permission = section === "permissions" ? data.permissions.find(entry => entry.id === id) : undefined;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const values = new FormData(form);
    // Passwords stay in the submitted form only, never React state or query caches.
    form.querySelectorAll<HTMLInputElement>('input[type="password"]').forEach(input => { input.value = ""; });
    const value = (key: string) => String(values.get(key) ?? "");
    const ids = (key: string) => values.getAll(key).map(String);
    const payload = section === "users"
      ? { name: value("name"), email: value("email"), role_ids: ids("role_ids"), group_ids: ids("group_ids"),
          ...(id ? { is_active: values.has("is_active") } : { username: value("username"), password: value("password") }) }
      : section === "permissions" ? { key: value("key"), description: value("description") }
        : { name: value("name"), description: value("description"),
            ...(section === "groups" ? { role_ids: ids("role_ids") } : { permission_ids: ids("permission_ids") }) };
    void act(() => section === "users" ? accountClient.saveUser(id, payload, csrf) : accountClient.save(section, id, payload, csrf))
      .then(ok => { if (ok) close(); });
  }
  return <form className={styles.editor} onSubmit={submit}>
    <h3>{t((id ? "Edit " : "Create ") + (section === "users" ? "account" : section.slice(0, -1)))}</h3>
    <fieldset disabled={busy} className={styles.fields}>
      {section === "users" && !id && <label>{t("Username")}<input name="username" required minLength={3} maxLength={64}
        pattern={"[a-z0-9][a-z0-9._\\-]{2,63}"} autoComplete="off" /><small>{t("3–64 lowercase letters, numbers, dots, underscores, or hyphens.")}</small></label>}
      {section === "permissions" ? <label>{t("Permission key")}<input name="key" defaultValue={permission?.key} required
        pattern={"[a-z][a-z0-9_.:\\-]{1,99}"} minLength={2} maxLength={100} placeholder="tasks.read" /></label>
        : <label>{t("Name")}<input name="name" defaultValue={item && "name" in item ? item.name : ""} required maxLength={section === "users" ? 200 : 100} /></label>}
      {section === "users" ? <>
        <label>{t("Email (optional)")}<input name="email" type="email" defaultValue={user?.email} maxLength={320} /></label>
        {!id && <PasswordInput />}
        {id && <label className={styles.checkbox}><input name="is_active" type="checkbox" defaultChecked={user?.is_active} />{t("Active account")}</label>}
        <Checks title={t("Groups")} name="group_ids" options={data.groups.map(g => ({ id: g.id, label: g.name }))} selected={user?.group_ids} />
      </> : <label>{t("Description")}<input name="description" defaultValue={item && "description" in item ? item.description : ""} maxLength={500} /></label>}
      {(section === "users" || section === "groups") && <Checks title={section === "users" ? t("Direct roles") : t("Roles for group members")}
        name="role_ids" options={data.roles.map(r => ({ id: r.id, label: r.name }))} selected={user?.role_ids ?? group?.role_ids} />}
      {section === "roles" && <Checks title={t("Permissions")} name="permission_ids"
        options={data.permissions.map(p => ({ id: p.id, label: p.key }))} selected={role?.permission_ids} />}
    </fieldset>
    <div className={styles.actions}><button disabled={busy}>{t("Save")}</button><button type="button" disabled={busy} onClick={close}>{t("Cancel")}</button></div>
  </form>;
}
