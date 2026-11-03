package io.github.tabear25.kindle2notion;

import java.io.UnsupportedEncodingException;
import java.net.URLDecoder;

/** Plain-JVM checks for {@link LaunchUrls}; run by `android/build.sh test`. */
public final class LaunchUrlsTest {

    private static int failures;

    public static void main(String[] args) throws Exception {
        // normalizeBase: what the setup screen accepts
        same(LaunchUrls.normalizeBase("https://xxxx.vercel.app"), "https://xxxx.vercel.app", "plain origin");
        same(LaunchUrls.normalizeBase("  https://XXXX.Vercel.app/  "), "https://xxxx.vercel.app", "trim, lower-case host, drop slash");
        same(LaunchUrls.normalizeBase("xxxx.vercel.app"), "https://xxxx.vercel.app", "scheme added when typed without one");
        same(LaunchUrls.normalizeBase("https://xxxx.vercel.app/static/app.js?v=1#x"), "https://xxxx.vercel.app", "path, query, fragment dropped");
        same(LaunchUrls.normalizeBase("https://example.com:8443/"), "https://example.com:8443", "non-default port kept");
        same(LaunchUrls.normalizeBase("https://example.com:443"), "https://example.com", "default port dropped");
        same(LaunchUrls.normalizeBase("http://xxxx.vercel.app"), null, "http refused (Basic auth would travel in clear)");
        same(LaunchUrls.normalizeBase("https://user:pass@xxxx.vercel.app"), null, "credentials in the URL refused");
        same(LaunchUrls.normalizeBase("ftp://xxxx.vercel.app"), null, "other schemes refused");
        same(LaunchUrls.normalizeBase("javascript:alert(1)"), null, "javascript: refused");
        same(LaunchUrls.normalizeBase("   "), null, "blank");
        same(LaunchUrls.normalizeBase(null), null, "null");

        // forLaunch: the URLs the page understands (frontend/static/app.js consumeLaunchParams)
        String base = "https://xxxx.vercel.app";
        same(LaunchUrls.forLaunch(base, null, null, null), base + "/", "no action");
        same(LaunchUrls.forLaunch(base, "android.intent.action.MAIN", null, null), base + "/", "launcher icon");
        same(LaunchUrls.forLaunch(base, LaunchUrls.ACTION_SYNC, null, null), base + "/?action=sync", "sync shortcut / widget");
        same(LaunchUrls.forLaunch(base, LaunchUrls.ACTION_MANUAL, null, null), base + "/?action=manual", "manual shortcut / widget");

        String text = "人間の判断は\n2つ & 3つ = 5? #タグ 100%";
        String subject = "ファスト&スロー（上）";
        String shared = LaunchUrls.forLaunch(base, LaunchUrls.ACTION_SEND, text, subject);
        check(shared.startsWith(base + "/?share_title="), "share opens the root with share params: " + shared);
        check(shared.split("&").length == 2, "shared text cannot inject extra parameters: " + shared);
        same(param(shared, "share_text"), text, "share_text round-trips (UTF-8, newline, & = ? # %)");
        same(param(shared, "share_title"), subject, "share_title round-trips");
        same(LaunchUrls.forLaunch(base, LaunchUrls.ACTION_SEND, null, null),
                base + "/?share_title=&share_text=", "share without extras");

        // forcesReload: only explicit launches replace the page
        check(LaunchUrls.forcesReload(LaunchUrls.ACTION_SYNC), "sync reloads");
        check(LaunchUrls.forcesReload(LaunchUrls.ACTION_MANUAL), "manual reloads");
        check(LaunchUrls.forcesReload(LaunchUrls.ACTION_SEND), "share reloads");
        check(!LaunchUrls.forcesReload("android.intent.action.MAIN"), "launcher tap keeps the page");
        check(!LaunchUrls.forcesReload(null), "no action keeps the page");

        // isInternal: what may load inside the app
        check(LaunchUrls.isInternal(base, base + "/?action=sync"), "same origin stays in the app");
        check(LaunchUrls.isInternal(base, "https://XXXX.vercel.app/x"), "host match is case-insensitive");
        check(!LaunchUrls.isInternal(base, "https://evil.example/"), "other host goes to the browser");
        check(!LaunchUrls.isInternal(base, "https://xxxx.vercel.app.evil.example/"), "suffix trick goes to the browser");
        check(!LaunchUrls.isInternal(base, "https://evil.example/https://xxxx.vercel.app"), "origin in the path goes to the browser");
        check(!LaunchUrls.isInternal(base, "http://xxxx.vercel.app/"), "http downgrade goes to the browser");
        check(!LaunchUrls.isInternal(base, "https://xxxx.vercel.app:8443/"), "other port goes to the browser");
        check(!LaunchUrls.isInternal(base, "intent://scan/#Intent;scheme=zxing;end"), "intent: is not internal");
        check(!LaunchUrls.isInternal(base, "about:blank"), "about:blank is not internal");

        if (failures > 0) {
            System.err.println("LaunchUrlsTest: " + failures + " failure(s)");
            System.exit(1);
        }
        System.out.println("LaunchUrlsTest: all checks passed");
    }

    private static String param(String url, String name) throws UnsupportedEncodingException {
        String query = url.substring(url.indexOf('?') + 1);
        for (String pair : query.split("&")) {
            int eq = pair.indexOf('=');
            if (pair.substring(0, eq).equals(name)) {
                return URLDecoder.decode(pair.substring(eq + 1), "UTF-8");
            }
        }
        return null;
    }

    private static void same(Object actual, Object expected, String what) {
        boolean ok = expected == null ? actual == null : expected.equals(actual);
        check(ok, what + " (expected " + expected + ", got " + actual + ")");
    }

    private static void check(boolean ok, String what) {
        if (!ok) {
            failures++;
            System.err.println("FAIL: " + what);
        }
    }
}
