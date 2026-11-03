package io.github.tabear25.kindle2notion;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

/**
 * Home-screen widget with two buttons: start a Kindle sync, or open the
 * manual-entry screen. Both just launch {@link MainActivity}; the page does
 * the rest, so the widget never needs periodic updates.
 */
public class SyncWidgetProvider extends AppWidgetProvider {

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] appWidgetIds) {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_sync);
        views.setOnClickPendingIntent(R.id.widget_sync, launch(context, LaunchUrls.ACTION_SYNC, 1));
        views.setOnClickPendingIntent(R.id.widget_manual, launch(context, LaunchUrls.ACTION_MANUAL, 2));
        manager.updateAppWidget(appWidgetIds, views);
    }

    private static PendingIntent launch(Context context, String action, int requestCode) {
        Intent intent = new Intent(context, MainActivity.class)
                .setAction(action)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return PendingIntent.getActivity(context, requestCode, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
}
