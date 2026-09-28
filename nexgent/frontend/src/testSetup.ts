import { beforeEach } from "vitest";
import { useLanguage } from "./shared/i18n";

// Existing workflow assertions explicitly exercise English. Locale tests also
// cover Korean and initialize fresh modules to verify the persisted default.
beforeEach(() => useLanguage.setState({ language: "en" }));
