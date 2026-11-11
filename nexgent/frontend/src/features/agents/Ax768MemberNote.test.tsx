import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { Ax768WorkbenchPage } from "./Ax768WorkbenchPage";
import { useAx768Store } from "../../shared/state/useAx768Store";
import { useLanguage } from "../../shared/i18n";
vi.mock("../../shared/state/useAx768Store", async importOriginal => {
 const actual = await importOriginal<typeof import("../../shared/state/useAx768Store")>();
 return {...actual, useAx768Store: Object.assign(() => actual.useAx768Store.getState(), actual.useAx768Store)};
});
afterEach(()=>useAx768Store.getState().reset());
it("shows the new test as a real note replacement, without sheet formatting copy",()=>{
 useLanguage.setState({language:"en"});useAx768Store.getState().selectCase("member_note");
 const html=renderToStaticMarkup(<Ax768WorkbenchPage/>);
 expect(html).toContain('value="member_note" selected=""');
 expect(html).toContain('Find member and replace notes');
 expect(html).toContain('Replaces General notes with the entered text');
 expect(html).toContain('This test saves a real member note');
 expect(html).not.toContain('Search and apply yellow');
});
