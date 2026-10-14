import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  bahmniUserCookieNeedsRewrite,
  encodeBahmniUserCookie,
  usernameFromBahmniCookie,
} from "./bahmniUserCookie.ts";

describe("encodeBahmniUserCookie", () => {
  it("stores the username as a JSON string, the way Bahmni login writes bahmni.user", () => {
    assert.equal(encodeBahmniUserCookie("clinical.user"), '"clinical.user"');
    assert.doesNotThrow(() => JSON.parse(encodeBahmniUserCookie("clinical.user")));
    assert.equal(JSON.parse(encodeBahmniUserCookie("clinical.user")), "clinical.user");
  });

  it("does not store a bare username that JSON.parse would reject", () => {
    assert.notEqual(encodeBahmniUserCookie("clinical.user"), "clinical.user");
    assert.throws(() => JSON.parse("clinical.user"), SyntaxError);
  });
});

describe("usernameFromBahmniCookie", () => {
  it("reads a Bahmni JSON string username", () => {
    assert.equal(usernameFromBahmniCookie('"clinical.user"'), "clinical.user");
  });

  it("reads a leftover plain username from an older Hospital EMR login", () => {
    assert.equal(usernameFromBahmniCookie("clinical.user"), "clinical.user");
  });

  it("reads a JSON object that only carries username", () => {
    assert.equal(usernameFromBahmniCookie('{"username":"clinical.user"}'), "clinical.user");
  });

  it("returns null when the cookie is missing or blank", () => {
    assert.equal(usernameFromBahmniCookie(null), null);
    assert.equal(usernameFromBahmniCookie(""), null);
    assert.equal(usernameFromBahmniCookie("   "), null);
  });

  it("returns null for malformed JSON objects instead of guessing", () => {
    assert.equal(usernameFromBahmniCookie("{not-json"), null);
    assert.equal(usernameFromBahmniCookie("[1,2"), null);
    assert.equal(usernameFromBahmniCookie("42"), null);
  });
});

describe("bahmniUserCookieNeedsRewrite", () => {
  it("rewrites a plain username so Bahmni Clinical can parse it", () => {
    assert.equal(bahmniUserCookieNeedsRewrite("clinical.user", "clinical.user"), true);
  });

  it("leaves a correctly encoded Bahmni username alone", () => {
    assert.equal(bahmniUserCookieNeedsRewrite('"clinical.user"', "clinical.user"), false);
  });
});
