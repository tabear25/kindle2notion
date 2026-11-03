package io.github.tabear25.kindle2notion;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * Hosts the deployed web UI in a WebView. Everything about syncing — the
 * cold-start wait, progress, 2FA, manual entry — lives in that page; this
 * activity only maps launches to its URLs (see {@link LaunchUrls}) and
 * remembers which page to open.
 */
public class MainActivity extends Activity {

    private static final String PREFS = "k2n";
    private static final String KEY_BASE_URL = "base_url";
    /** Lets the page recognise the app (frontend/static/app.js: IN_ANDROID_APP). */
    private static final String USER_AGENT_TOKEN = "K2NAndroid/1.0.0";
    /** window.K2NAndroid in the page. */
    private static final String BRIDGE_NAME = "K2NAndroid";

    private WebView webView;
    private View errorView;
    private View setupView;
    private EditText setupInput;
    private TextView setupError;
    private Button setupCancel;

    private String baseUrl;
    private boolean pageLoaded;
    private boolean loadFailed;
    /** A launch that arrived before the URL was set; replayed once it is saved. */
    private Intent pendingLaunch;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        baseUrl = LaunchUrls.normalizeBase(prefs().getString(KEY_BASE_URL, null));

        FrameLayout root = new FrameLayout(this);
        webView = buildWebView();
        errorView = buildErrorView();
        setupView = buildSetupView();
        root.addView(webView, fill());
        root.addView(errorView, fill());
        root.addView(setupView, fill());
        setContentView(root);

        handleLaunch(getIntent(), true);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleLaunch(intent, false);
    }

    @Override
    protected void onResume() {
        super.onResume();
        webView.onResume();
    }

    @Override
    protected void onPause() {
        webView.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        ViewGroup parent = (ViewGroup) webView.getParent();
        if (parent != null) {
            parent.removeView(webView);
        }
        webView.destroy();
        super.onDestroy();
    }

    @Override
    @SuppressWarnings("deprecation") // still delivered for targetSdk 34 without the predictive-back opt-in
    public void onBackPressed() {
        if (setupView.getVisibility() == View.VISIBLE && baseUrl != null) {
            cancelSetup();
            return;
        }
        if (webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    // ------------------------------------------------------------------
    // Launches
    // ------------------------------------------------------------------

    private void handleLaunch(Intent intent, boolean firstLaunch) {
        String action = intent == null ? null : intent.getAction();
        if (LaunchUrls.ACTION_SETTINGS.equals(action)) {
            showSetup();
            return;
        }
        if (baseUrl == null) {
            pendingLaunch = intent;
            showSetup();
            return;
        }
        if (!firstLaunch && pageLoaded && !LaunchUrls.forcesReload(action)) {
            return; // back via the launcher icon: keep whatever the page shows
        }
        open(LaunchUrls.forLaunch(baseUrl, action,
                extraText(intent, Intent.EXTRA_TEXT), extraText(intent, Intent.EXTRA_SUBJECT)));
    }

    private static CharSequence extraText(Intent intent, String name) {
        return intent == null ? null : intent.getCharSequenceExtra(name);
    }

    private void open(String url) {
        hideKeyboard();
        setupView.setVisibility(View.GONE);
        errorView.setVisibility(View.GONE);
        webView.loadUrl(url);
    }

    private void openExternally(String url) {
        Uri uri = Uri.parse(url);
        String scheme = uri.getScheme();
        if (!"https".equalsIgnoreCase(scheme) && !"http".equalsIgnoreCase(scheme)) {
            return; // intent:, javascript:, file: ... are never handed to other apps
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException ignored) {
            // no browser installed: nothing sensible left to do
        }
    }

    // ------------------------------------------------------------------
    // WebView
    // ------------------------------------------------------------------

    private WebView buildWebView() {
        WebView view = new WebView(this);
        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true); // 接続設定 lives in localStorage
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setSupportMultipleWindows(false);
        settings.setUserAgentString(settings.getUserAgentString() + " " + USER_AGENT_TOKEN);
        view.setWebChromeClient(new WebChromeClient()); // shows the page's alert() dialogs
        view.setWebViewClient(new PageClient());
        view.addJavascriptInterface(new Bridge(), BRIDGE_NAME);
        return view;
    }

    private final class PageClient extends WebViewClient {
        @Override
        @SuppressWarnings("deprecation") // the String overload exists at every supported level and is still called
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            if (baseUrl != null && LaunchUrls.isInternal(baseUrl, url)) {
                return false;
            }
            openExternally(url);
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            loadFailed = false;
            // A new page never inherits a keep-screen-on request it cannot release.
            setKeepScreenOn(false);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            pageLoaded = !loadFailed;
            // A single-page UI: entries left by earlier widget / shortcut loads
            // would only make Back replay stale pages, so Back always leaves.
            view.clearHistory();
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                loadFailed = true;
                pageLoaded = false;
                errorView.setVisibility(View.VISIBLE);
            }
        }
    }

    /**
     * Exposed to the page as window.K2NAndroid. The WebView has no Screen Wake
     * Lock API, so the page asks for the window flag instead while it waits for
     * the backend to wake up (frontend/static/app.js: acquireWakeLock).
     */
    private final class Bridge {
        @JavascriptInterface
        public void setKeepScreenOn(final boolean on) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    MainActivity.this.setKeepScreenOn(on);
                }
            });
        }
    }

    private void setKeepScreenOn(boolean on) {
        if (on) {
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        } else {
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        }
    }

    // ------------------------------------------------------------------
    // Setup: which page to open (the Vercel URL)
    // ------------------------------------------------------------------

    private void showSetup() {
        setupInput.setText(baseUrl == null ? "" : baseUrl);
        setupInput.setSelection(setupInput.getText().length());
        setupError.setVisibility(View.GONE);
        setupCancel.setVisibility(baseUrl == null ? View.GONE : View.VISIBLE);
        errorView.setVisibility(View.GONE);
        setupView.setVisibility(View.VISIBLE);
        setupInput.requestFocus();
    }

    private void saveSetup() {
        String normalized = LaunchUrls.normalizeBase(setupInput.getText().toString());
        if (normalized == null) {
            setupError.setVisibility(View.VISIBLE);
            return;
        }
        baseUrl = normalized;
        prefs().edit().putString(KEY_BASE_URL, normalized).apply();
        Intent launch = pendingLaunch;
        pendingLaunch = null;
        String action = launch == null ? null : launch.getAction();
        open(LaunchUrls.forLaunch(baseUrl, action,
                extraText(launch, Intent.EXTRA_TEXT), extraText(launch, Intent.EXTRA_SUBJECT)));
    }

    private void cancelSetup() {
        hideKeyboard();
        setupView.setVisibility(View.GONE);
        if (!pageLoaded) {
            open(LaunchUrls.forLaunch(baseUrl, null, null, null));
        }
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    private void hideKeyboard() {
        InputMethodManager keyboard = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
        if (keyboard != null && setupInput != null) {
            keyboard.hideSoftInputFromWindow(setupInput.getWindowToken(), 0);
        }
    }

    // ------------------------------------------------------------------
    // Native screens (built in code: two small views do not need layouts)
    // ------------------------------------------------------------------

    private View buildSetupView() {
        LinearLayout column = column();
        column.addView(text(R.string.setup_title, 22, R.color.text_primary, true));
        column.addView(spaced(text(R.string.setup_message, 15, R.color.text_secondary, false), 8));

        setupInput = new EditText(this);
        setupInput.setHint(R.string.setup_hint);
        setupInput.setSingleLine(true);
        setupInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        setupInput.setImeOptions(EditorInfo.IME_ACTION_GO);
        setupInput.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override
            public boolean onEditorAction(TextView view, int actionId, KeyEvent event) {
                saveSetup();
                return true;
            }
        });
        column.addView(spaced(setupInput, 20));

        setupError = text(R.string.setup_invalid, 14, R.color.danger, false);
        setupError.setVisibility(View.GONE);
        column.addView(spaced(setupError, 8));

        column.addView(spaced(button(R.string.setup_save, true, new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                saveSetup();
            }
        }), 16));
        setupCancel = button(R.string.setup_cancel, false, new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                cancelSetup();
            }
        });
        column.addView(spaced(setupCancel, 10));
        column.addView(spaced(text(R.string.setup_note, 13, R.color.text_secondary, false), 24));

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(getColor(R.color.background));
        scroll.setClickable(true); // nothing reaches the WebView underneath
        scroll.setVisibility(View.GONE);
        scroll.addView(column);
        return scroll;
    }

    private View buildErrorView() {
        LinearLayout column = column();
        column.setGravity(Gravity.CENTER_VERTICAL);
        column.setBackgroundColor(getColor(R.color.background));
        column.setClickable(true);
        column.addView(text(R.string.error_title, 20, R.color.text_primary, true));
        column.addView(spaced(text(R.string.error_message, 15, R.color.text_secondary, false), 8));
        column.addView(spaced(button(R.string.error_retry, true, new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                errorView.setVisibility(View.GONE);
                webView.reload();
            }
        }), 20));
        column.addView(spaced(button(R.string.error_change_url, false, new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                showSetup();
            }
        }), 10));
        column.setVisibility(View.GONE);
        return column;
    }

    private LinearLayout column() {
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(dp(24), dp(32), dp(24), dp(32));
        return column;
    }

    private TextView text(int textRes, int sp, int colorRes, boolean bold) {
        TextView view = new TextView(this);
        view.setText(textRes);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        view.setTextColor(getColor(colorRes));
        view.setLineSpacing(0, 1.2f);
        if (bold) {
            view.setTypeface(Typeface.DEFAULT_BOLD);
        }
        return view;
    }

    private Button button(int textRes, boolean primary, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(textRes);
        button.setAllCaps(false);
        button.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        button.setTextColor(primary ? 0xFFFFFFFF : getColor(R.color.accent_dark));
        GradientDrawable background = new GradientDrawable();
        background.setColor(getColor(primary ? R.color.accent : R.color.accent_soft));
        background.setCornerRadius(dp(8));
        button.setBackground(background);
        button.setMinHeight(dp(48));
        button.setOnClickListener(listener);
        return button;
    }

    private View spaced(View view, int topDp) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(topDp);
        view.setLayoutParams(params);
        return view;
    }

    private static FrameLayout.LayoutParams fill() {
        return new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, getResources().getDisplayMetrics()));
    }
}
