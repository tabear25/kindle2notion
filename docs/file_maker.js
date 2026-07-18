function createSpreadsheets() {
  const parentFolderId = "1Ek_BHJgTFvWNQWUAO1uCDaOtEGewfrNQ"; // kindle2notion（FOLDER_ID）
  const parentFolder = DriveApp.getFolderById(parentFolderId);

  // notebooklm サブフォルダを取得。無ければ作成する
  const subFolders = parentFolder.getFoldersByName("notebooklm");
  const destFolder = subFolders.hasNext() ? subFolders.next() : parentFolder.createFolder("notebooklm");

  // k2n_index + k2n_vol_01〜k2n_vol_99 の計100件を生成
  const fileNames = ["k2n_index"];
  for (let i = 1; i <= 99; i++) {
    fileNames.push("k2n_vol_" + ("0" + i).slice(-2));
  }

  let created = 0;
  let skipped = 0;

  fileNames.forEach(name => {
    if (destFolder.getFilesByName(name).hasNext()) {
      console.log(`Skip（既存）: ${name}`);
      skipped++;
      return;
    }
    const ss = SpreadsheetApp.create(name);
    DriveApp.getFileById(ss.getId()).moveTo(destFolder);
    console.log(`Created: ${name}`);
    created++;
  });

  console.log(`完了！ 作成 ${created} 件 / スキップ ${skipped} 件 / 合計 ${fileNames.length} 件`);
}