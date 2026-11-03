package io.github.tabear25.kindle2notion;

import java.io.UnsupportedEncodingException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URLEncoder;
import java.util.Locale;

/**
 * Turns every way into the app (launcher, shortcut, widget, share sheet) into
 * a URL of the web UI. The page reads the same parameters the installable web
 * app uses (frontend/static/app.js: consumeLaunchParams), so the native side
 * stays a thin shell.
 *
 * Plain Java on purpose (no android.* imports): android/test runs it on an
 * ordinary JVM.
 */
final class LaunchUrls {

    static final String ACTION_SYNC = "io.github.tabear25.kindle2notion.action.SYNC";
    static final String ACTION_MANUAL = "io.github.tabear25.kindle2notion.action.MANUAL";
    static final String ACTION_SETTINGS = "io.github.tabear25.kindle2notion.action.SETTINGS";
    static final String ACTION_SEND = "android.intent.action.SEND";

    private LaunchUrls() {
    }

    /**
     * Normalises what the user typed into the origin the app will load:
     * "xxxx.vercel.app/" or "https://xxxx.vercel.app/foo?x" both become
     * "https://xxxx.vercel.app". Returns null for anything that is not a
     * plain https origin — the page sends Basic-auth credentials, so http and
     * URLs carrying user info are refused.
     */
    static String normalizeBase(String typed) {
        if (typed == null) {
            return null;
        }
        String text = typed.trim();
        if (text.isEmpty()) {
            return null;
        }
        if (!text.contains("://")) {
            text = "https://" + text;
        }
        return httpsOrigin(text);
    }

    /** The URL a launch should open. {@code base} comes from {@link #normalizeBase}. */
    static String forLaunch(String base, String action, CharSequence sharedText, CharSequence sharedSubject) {
        if (ACTION_SYNC.equals(action)) {
            return base + "/?action=sync";
        }
        if (ACTION_MANUAL.equals(action)) {
            return base + "/?action=manual";
        }
        if (ACTION_SEND.equals(action)) {
            return base + "/?share_title=" + encode(sharedSubject) + "&share_text=" + encode(sharedText);
        }
        return base + "/";
    }

    /**
     * Launches that must (re)load the page. A plain launcher tap on a running
     * app must not: it would throw away a sync shown in progress.
     */
    static boolean forcesReload(String action) {
        return ACTION_SYNC.equals(action) || ACTION_MANUAL.equals(action) || ACTION_SEND.equals(action);
    }

    /** Same origin as the configured page: stays in the app. Anything else opens in the browser. */
    static boolean isInternal(String base, String url) {
        String origin = httpsOrigin(url);
        return origin != null && origin.equals(base);
    }

    private static String httpsOrigin(String url) {
        URI uri;
        try {
            uri = new URI(url);
        } catch (URISyntaxException e) {
            return null;
        }
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getRawUserInfo() != null) {
            return null;
        }
        String host = uri.getHost();
        if (host == null || host.isEmpty()) {
            return null;
        }
        int port = uri.getPort();
        return "https://" + host.toLowerCase(Locale.ROOT) + (port > 0 && port != 443 ? ":" + port : "");
    }

    private static String encode(CharSequence value) {
        try {
            return URLEncoder.encode(value == null ? "" : value.toString(), "UTF-8");
        } catch (UnsupportedEncodingException e) {
            throw new AssertionError(e); // UTF-8 is always available
        }
    }
}
