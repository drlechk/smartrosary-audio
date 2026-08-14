import { promises as fs } from 'node:fs';
import path from 'node:path';

const repoRoot = path.resolve(new URL('..', import.meta.url).pathname);
const textsPath = path.join(repoRoot, 'basic-prayer-texts.json');
const audioLanguagesDir = path.join(repoRoot, 'audio-languages');
const outputPath = path.join(repoRoot, 'audio-data.json');
const siteDirArg = process.argv.find((arg) => arg.startsWith('--site-dir='));
const siteDir = siteDirArg ? path.resolve(repoRoot, siteDirArg.split('=').slice(1).join('=')) : null;

if (siteDir && (siteDir === repoRoot || !siteDir.startsWith(`${repoRoot}${path.sep}`))) {
  throw new Error('--site-dir must point to a staging directory inside this repository');
}

const languageNames = {
  pl: 'Polski',
  en: 'English',
  de: 'Deutsch',
  fr: 'Francais',
  es: 'Espanol',
  pt: 'Portugues'
};

const languageOrder = ['pl', 'en', 'de', 'fr', 'es', 'pt'];

const clipTitles = {
  '010': "Apostles' Creed",
  '020': 'Our Father, first part',
  '021': 'Our Father, second part',
  '030': 'Hail Mary, first part',
  '031': 'Hail Mary, second part',
  '040': 'Glory Be',
  '050': 'Fatima prayer',
  '060': 'Divine Mercy Chaplet: Eternal Father prayer',
  '070': 'Divine Mercy Chaplet: For the sake of His sorrowful Passion',
  '071': 'Divine Mercy Chaplet: mercy response',
  '080': 'Divine Mercy Chaplet: Holy God prayer',
  '090': 'Divine Mercy Chaplet: Jesus, I trust in You',
  mT1: 'Joyful Mysteries set title',
  mT2: 'Luminous Mysteries set title',
  mT3: 'Sorrowful Mysteries set title',
  mT4: 'Glorious Mysteries set title',
  mT5: 'Divine Mercy Chaplet title'
};

const mysterySetNames = {
  1: 'Joyful Mystery',
  2: 'Luminous Mystery',
  3: 'Sorrowful Mystery',
  4: 'Glorious Mystery'
};

const fixedOrder = [
  '010', '020', '021', '030', '031', '040', '050',
  '060', '070', '071', '080', '090',
  'mT1', 'mT2', 'mT3', 'mT4', 'mT5'
];

function clipSortKey(id) {
  const fixedIndex = fixedOrder.indexOf(id);
  if (fixedIndex !== -1) return fixedIndex;
  const mysteryMatch = /^m([1-5])([1-4])$/.exec(id);
  if (mysteryMatch) {
    const mysteryNumber = Number(mysteryMatch[1]);
    const setNumber = Number(mysteryMatch[2]);
    return fixedOrder.length + (setNumber - 1) * 5 + mysteryNumber - 1;
  }
  return fixedOrder.length + 100 + id.charCodeAt(0);
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, 'utf8'));
}

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function getAudioLanguageTexts(languageCode) {
  const filePath = path.join(audioLanguagesDir, `${languageCode}.json`);
  if (!(await exists(filePath))) return {};
  const data = await readJson(filePath);
  return data.texts || {};
}

function getClipTitle(id) {
  if (clipTitles[id]) return clipTitles[id];
  const mysteryMatch = /^m([1-5])([1-4])$/.exec(id);
  if (!mysteryMatch) return id;
  const mysteryNumber = Number(mysteryMatch[1]);
  const setNumber = Number(mysteryMatch[2]);
  return `${mysterySetNames[setNumber]} ${mysteryNumber}`;
}

function getClipGroup(id) {
  if (/^\d/.test(id) && Number(id) < 60) return 'Rosary prayers';
  if (/^\d/.test(id)) return 'Divine Mercy Chaplet';
  if (/^mT/.test(id)) return 'Mystery set titles';
  return 'Mystery titles';
}

function variantSort(a, b) {
  return a.voice.localeCompare(b.voice) || a.id.localeCompare(b.id);
}

async function copyFileIntoSite(relativeFile) {
  if (!siteDir) return;
  const source = path.join(repoRoot, relativeFile);
  const target = path.join(siteDir, relativeFile);
  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.copyFile(source, target);
}

async function copyPublicFiles(voiceIds) {
  if (!siteDir) return;
  await fs.rm(siteDir, { recursive: true, force: true });
  await fs.mkdir(siteDir, { recursive: true });
  await copyFileIntoSite('index.html');
  await copyFileIntoSite('favicon.svg');
  await copyFileIntoSite('audio-data.json');
  for (const voiceId of voiceIds) {
    const sourceDir = path.join(repoRoot, voiceId);
    const targetDir = path.join(siteDir, voiceId);
    await fs.mkdir(targetDir, { recursive: true });
    const files = (await fs.readdir(sourceDir)).filter((name) => name.endsWith('.mp3'));
    for (const file of files) {
      await fs.copyFile(path.join(sourceDir, file), path.join(targetDir, file));
    }
  }
}

async function build() {
  const basic = await readJson(textsPath);
  const voices = basic.voices || {};
  const languages = new Map();
  const publicVoiceIds = [];

  for (const [voiceId, voiceInfo] of Object.entries(voices)) {
    const languageCode = voiceInfo.texts;
    const voiceDir = path.join(repoRoot, voiceId);
    if (!(await exists(voiceDir))) continue;

    const files = (await fs.readdir(voiceDir))
      .filter((name) => name.endsWith('.mp3'))
      .sort((a, b) => clipSortKey(path.basename(a, '.mp3')) - clipSortKey(path.basename(b, '.mp3')));

    if (!files.length) continue;
    publicVoiceIds.push(voiceId);

    const audioTexts = await getAudioLanguageTexts(languageCode);
    const clips = await Promise.all(files.map(async (fileName) => {
      const id = path.basename(fileName, '.mp3');
      const stat = await fs.stat(path.join(voiceDir, fileName));
      return {
        id,
        file: `${voiceId}/${fileName}`,
        title: getClipTitle(id),
        group: getClipGroup(id),
        text: basic.texts?.[languageCode]?.[id] || audioTexts[id] || '',
        bytes: stat.size
      };
    }));

    if (!languages.has(languageCode)) {
      languages.set(languageCode, {
        code: languageCode,
        name: languageNames[languageCode] || languageCode.toUpperCase(),
        variants: []
      });
    }

    languages.get(languageCode).variants.push({
      id: voiceId,
      voice: voiceInfo.voice || voiceId,
      language: voiceInfo.language || languageCode,
      clipCount: clips.length,
      clips
    });
  }

  const data = {
    languages: Array.from(languages.values())
      .sort((a, b) => {
        const aOrder = languageOrder.indexOf(a.code);
        const bOrder = languageOrder.indexOf(b.code);
        const orderDiff = (aOrder === -1 ? 999 : aOrder) - (bOrder === -1 ? 999 : bOrder);
        return orderDiff || a.name.localeCompare(b.name);
      })
      .map((language) => ({
        ...language,
        variants: language.variants.sort(variantSort)
      }))
  };

  await fs.writeFile(outputPath, `${JSON.stringify(data, null, 2)}\n`);
  await copyPublicFiles(publicVoiceIds);
  console.log(`Wrote ${path.relative(repoRoot, outputPath)} with ${data.languages.length} languages.`);
  if (siteDir) console.log(`Prepared ${path.relative(repoRoot, siteDir)} for GitHub Pages.`);
}

build().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
