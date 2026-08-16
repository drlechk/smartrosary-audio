import { promises as fs } from 'node:fs';
import path from 'node:path';

const repoRoot = path.resolve(new URL('..', import.meta.url).pathname);
const textsPath = path.join(repoRoot, 'basic-prayer-texts.json');
const audioLanguagesDir = path.join(repoRoot, 'audio-languages');
const audioFsBuilderPath = path.join(repoRoot, 'build_audiofs.py');
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
  fr: 'Français',
  es: 'Español',
  it: 'Italiano',
  pt: 'Português'
};

const languageOrder = ['pl', 'en', 'de', 'fr', 'es', 'it', 'pt'];

const clipTitles = {
  en: {
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
  },
  pl: {
    '010': 'Skład Apostolski',
    '020': 'Ojcze nasz, pierwsza część',
    '021': 'Ojcze nasz, druga część',
    '030': 'Zdrowaś Maryjo, pierwsza część',
    '031': 'Zdrowaś Maryjo, druga część',
    '040': 'Chwała Ojcu',
    '050': 'Modlitwa fatimska',
    '060': 'Koronka do Miłosierdzia Bożego: modlitwa Ojcze Przedwieczny',
    '070': 'Koronka do Miłosierdzia Bożego: Dla Jego bolesnej męki',
    '071': 'Koronka do Miłosierdzia Bożego: odpowiedź o miłosierdzie',
    '080': 'Koronka do Miłosierdzia Bożego: Święty Boże',
    '090': 'Koronka do Miłosierdzia Bożego: Jezu, ufam Tobie',
    mT1: 'Tytuł tajemnic radosnych',
    mT2: 'Tytuł tajemnic światła',
    mT3: 'Tytuł tajemnic bolesnych',
    mT4: 'Tytuł tajemnic chwalebnych',
    mT5: 'Tytuł Koronki do Miłosierdzia Bożego'
  },
  de: {
    '010': 'Apostolisches Glaubensbekenntnis',
    '020': 'Vaterunser, erster Teil',
    '021': 'Vaterunser, zweiter Teil',
    '030': 'Gegrüßet seist du, Maria, erster Teil',
    '031': 'Gegrüßet seist du, Maria, zweiter Teil',
    '040': 'Ehre sei dem Vater',
    '050': 'Fatima-Gebet',
    '060': 'Barmherzigkeitsrosenkranz: Ewiger Vater',
    '070': 'Barmherzigkeitsrosenkranz: Durch sein schmerzhaftes Leiden',
    '071': 'Barmherzigkeitsrosenkranz: Erbarme dich unser',
    '080': 'Barmherzigkeitsrosenkranz: Heiliger Gott',
    '090': 'Barmherzigkeitsrosenkranz: Jesus, ich vertraue auf dich',
    mT1: 'Titel der freudenreichen Geheimnisse',
    mT2: 'Titel der lichtreichen Geheimnisse',
    mT3: 'Titel der schmerzhaften Geheimnisse',
    mT4: 'Titel der glorreichen Geheimnisse',
    mT5: 'Titel des Barmherzigkeitsrosenkranzes'
  },
  es: {
    '010': 'Credo de los Apóstoles',
    '020': 'Padre nuestro, primera parte',
    '021': 'Padre nuestro, segunda parte',
    '030': 'Ave María, primera parte',
    '031': 'Ave María, segunda parte',
    '040': 'Gloria al Padre',
    '050': 'Oración de Fátima',
    '060': 'Coronilla de la Divina Misericordia: oración del Padre Eterno',
    '070': 'Coronilla de la Divina Misericordia: Por su dolorosa Pasión',
    '071': 'Coronilla de la Divina Misericordia: respuesta de misericordia',
    '080': 'Coronilla de la Divina Misericordia: Santo Dios',
    '090': 'Coronilla de la Divina Misericordia: Jesús, en ti confío',
    mT1: 'Título de los misterios gozosos',
    mT2: 'Título de los misterios luminosos',
    mT3: 'Título de los misterios dolorosos',
    mT4: 'Título de los misterios gloriosos',
    mT5: 'Título de la Coronilla de la Divina Misericordia'
  },
  fr: {
    '010': 'Symbole des Apôtres',
    '020': 'Notre Père, première partie',
    '021': 'Notre Père, deuxième partie',
    '030': 'Je vous salue Marie, première partie',
    '031': 'Je vous salue Marie, deuxième partie',
    '040': 'Gloire au Père',
    '050': 'Prière de Fatima',
    '060': 'Chapelet de la Divine Miséricorde : prière du Père Éternel',
    '070': 'Chapelet de la Divine Miséricorde : Par sa douloureuse Passion',
    '071': 'Chapelet de la Divine Miséricorde : réponse de miséricorde',
    '080': 'Chapelet de la Divine Miséricorde : Dieu Saint',
    '090': "Chapelet de la Divine Miséricorde : Jésus, j'ai confiance en toi",
    mT1: 'Titre des mystères joyeux',
    mT2: 'Titre des mystères lumineux',
    mT3: 'Titre des mystères douloureux',
    mT4: 'Titre des mystères glorieux',
    mT5: 'Titre du Chapelet de la Divine Miséricorde'
  },
  it: {
    '010': 'Credo degli Apostoli',
    '020': 'Padre nostro, prima parte',
    '021': 'Padre nostro, seconda parte',
    '030': 'Ave Maria, prima parte',
    '031': 'Ave Maria, seconda parte',
    '040': 'Gloria al Padre',
    '050': 'Preghiera di Fatima',
    '060': 'Coroncina della Divina Misericordia: preghiera dell\'Eterno Padre',
    '070': 'Coroncina della Divina Misericordia: Per la sua dolorosa Passione',
    '071': 'Coroncina della Divina Misericordia: risposta di misericordia',
    '080': 'Coroncina della Divina Misericordia: Santo Dio',
    '090': 'Coroncina della Divina Misericordia: Gesù, confido in Te',
    mT1: 'Titolo dei misteri gaudiosi',
    mT2: 'Titolo dei misteri luminosi',
    mT3: 'Titolo dei misteri dolorosi',
    mT4: 'Titolo dei misteri gloriosi',
    mT5: 'Titolo della Coroncina della Divina Misericordia'
  },
  pt: {
    '010': 'Credo dos Apóstolos',
    '020': 'Pai Nosso, primeira parte',
    '021': 'Pai Nosso, segunda parte',
    '030': 'Avé Maria, primeira parte',
    '031': 'Avé Maria, segunda parte',
    '040': 'Glória ao Pai',
    '050': 'Oração de Fátima',
    '060': 'Terço da Divina Misericórdia: oração do Pai Eterno',
    '070': 'Terço da Divina Misericórdia: Pela sua dolorosa Paixão',
    '071': 'Terço da Divina Misericórdia: resposta de misericórdia',
    '080': 'Terço da Divina Misericórdia: Deus Santo',
    '090': 'Terço da Divina Misericórdia: Jesus, eu confio em vós',
    mT1: 'Título dos mistérios gozosos',
    mT2: 'Título dos mistérios luminosos',
    mT3: 'Título dos mistérios dolorosos',
    mT4: 'Título dos mistérios gloriosos',
    mT5: 'Título do Terço da Divina Misericórdia'
  }
};

const mysterySetNames = {
  en: {
    1: 'Joyful Mystery',
    2: 'Luminous Mystery',
    3: 'Sorrowful Mystery',
    4: 'Glorious Mystery'
  },
  pl: {
    1: 'Tajemnica radosna',
    2: 'Tajemnica światła',
    3: 'Tajemnica bolesna',
    4: 'Tajemnica chwalebna'
  },
  de: {
    1: 'Freudenreiches Geheimnis',
    2: 'Lichtreiches Geheimnis',
    3: 'Schmerzhaftes Geheimnis',
    4: 'Glorreiches Geheimnis'
  },
  es: {
    1: 'Misterio gozoso',
    2: 'Misterio luminoso',
    3: 'Misterio doloroso',
    4: 'Misterio glorioso'
  },
  fr: {
    1: 'Mystère joyeux',
    2: 'Mystère lumineux',
    3: 'Mystère douloureux',
    4: 'Mystère glorieux'
  },
  it: {
    1: 'Mistero gaudioso',
    2: 'Mistero luminoso',
    3: 'Mistero doloroso',
    4: 'Mistero glorioso'
  },
  pt: {
    1: 'Mistério gozoso',
    2: 'Mistério luminoso',
    3: 'Mistério doloroso',
    4: 'Mistério glorioso'
  }
};

const clipGroups = {
  en: {
    rosary: 'Rosary prayers',
    chaplet: 'Divine Mercy Chaplet',
    setTitles: 'Mystery set titles',
    mysteryTitles: 'Mystery titles'
  },
  pl: {
    rosary: 'Modlitwy różańcowe',
    chaplet: 'Koronka do Miłosierdzia Bożego',
    setTitles: 'Tytuły zestawów tajemnic',
    mysteryTitles: 'Tytuły tajemnic'
  },
  de: {
    rosary: 'Rosenkranzgebete',
    chaplet: 'Barmherzigkeitsrosenkranz',
    setTitles: 'Titel der Geheimnisreihen',
    mysteryTitles: 'Titel der Geheimnisse'
  },
  es: {
    rosary: 'Oraciones del rosario',
    chaplet: 'Coronilla de la Divina Misericordia',
    setTitles: 'Títulos de grupos de misterios',
    mysteryTitles: 'Títulos de misterios'
  },
  fr: {
    rosary: 'Prières du chapelet',
    chaplet: 'Chapelet de la Divine Miséricorde',
    setTitles: 'Titres des séries de mystères',
    mysteryTitles: 'Titres des mystères'
  },
  it: {
    rosary: 'Preghiere del rosario',
    chaplet: 'Coroncina della Divina Misericordia',
    setTitles: 'Titoli delle serie di misteri',
    mysteryTitles: 'Titoli dei misteri'
  },
  pt: {
    rosary: 'Orações do rosário',
    chaplet: 'Terço da Divina Misericórdia',
    setTitles: 'Títulos dos conjuntos de mistérios',
    mysteryTitles: 'Títulos dos mistérios'
  }
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

async function getAudioVersion() {
  const source = await fs.readFile(audioFsBuilderPath, 'utf8');
  const match = source.match(/^DEFAULT_MANIFEST_VERSION\s*=\s*["']([^"']+)["']/m);
  return match ? match[1] : 'unknown';
}

function getClipTitle(id, languageCode) {
  const titles = clipTitles[languageCode] || clipTitles.en;
  if (titles[id]) return titles[id];
  const mysteryMatch = /^m([1-5])([1-4])$/.exec(id);
  if (!mysteryMatch) return id;
  const mysteryNumber = Number(mysteryMatch[1]);
  const setNumber = Number(mysteryMatch[2]);
  const setNames = mysterySetNames[languageCode] || mysterySetNames.en;
  return `${setNames[setNumber]} ${mysteryNumber}`;
}

function getClipGroup(id, languageCode) {
  const groups = clipGroups[languageCode] || clipGroups.en;
  if (/^\d/.test(id) && Number(id) < 60) return groups.rosary;
  if (/^\d/.test(id)) return groups.chaplet;
  if (/^mT/.test(id)) return groups.setTitles;
  return groups.mysteryTitles;
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
  const audioVersion = await getAudioVersion();
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
        title: getClipTitle(id, languageCode),
        group: getClipGroup(id, languageCode),
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
      version: audioVersion,
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
