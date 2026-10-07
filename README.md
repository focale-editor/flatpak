# Focale Flatpak

Dépôt public de distribution Flatpak de [Focale](https://focale-editor.app),
préparé pour **https://flatpak.focale-editor.app**. Il contient la configuration,
la clé publique et le workflow de publication, sans le code source de l’éditeur.
Les objets OSTree et les deltas sont stockés dans des pièces jointes de releases
GitHub, puis déployés sur Pages ; ils ne sont pas committés dans Git.

Après la première publication :

```bash
flatpak install --user https://flatpak.focale-editor.app/Focale.flatpakref
flatpak update --user app.focaleeditor.Focale
```

Le paquet x86_64 utilise Freedesktop 25.08 fourni par Flathub. Ses intégrations
au bureau comprennent le lanceur, les icônes, les formats d’image et le type
`.focale`. Les mises à jour passent par Flatpak et le gestionnaire de logiciels.

## Première mise en ligne

1. Créer `focale-editor/flatpak` **public**, avec ce contenu sur la branche `main`.
2. Choisir **Settings → Pages → Source: GitHub Actions**. Définir le domaine
   `flatpak.focale-editor.app`, avec un CNAME DNS vers `focale-editor.github.io`.
   Vérifier le domaine dans l’organisation et activer HTTPS une fois disponible.
3. Fournir à la compilation privée un token limité à ce dépôt, avec accès
   **Contents: Read and write** et **Actions: Read and write**. La publication
   téléverse les snapshots et déclenche `pages.yml` avec un tag immuable.
4. Fournir au workflow privé la sauvegarde de la clé GPG correspondant à
   `focale-flatpak.asc`. La clé privée n’a sa place ni dans ce dépôt, ni dans les
   artifacts publics, ni dans Pages.
5. Publier la première release depuis la compilation privée. Le déploiement
   vérifie le SHA-256, la signature du résumé et la signature du commit OSTree.

Les `.flatpakrepo` et `.flatpakref` sont générés lors du déploiement avec la clé
publique intégrée. Ne pas remplacer la clé entre deux versions : les clients
installés lui font confiance. Préparer une rotation explicite si elle devient
nécessaire. La clé ne prend pas en charge une collection P2P ; ce dépôt utilise
les mises à jour distantes habituelles.

## Snapshots et mises à jour

Le pipeline privé importe la version SDK dans le snapshot signé précédent,
signe le commit et le résumé, conserve deux niveaux d’historique et produit les
deltas. Chaque release contient `snapshot.json` et `Focale-flatpak-<version>.tar.gz`.
Une publication existante est immuable. Les workflows refusent de remettre une
ancienne version à la tête du canal stable.

GitHub Pages limite la taille des sites. Le pipeline refuse les snapshots dont
les fichiers dépassent 950 Mio, ce qui réserve une marge aux descripteurs. Si
l’application ou son historique dépasse ce budget, changer l’hébergement du
dépôt avant publication ; ne pas supprimer les signatures pour le réduire.

Pour vérifier les outils localement :

```bash
python3 -m unittest discover -s scripts -p '*_test.py'
python3 scripts/repository.py stage --snapshot build/Focale-flatpak-1.0.0+1.tar.gz \
  --metadata build/snapshot.json --output site
```

Les tests utilisent des dépôts OSTree et clés GPG temporaires. Ils vérifient
l’historique, les deltas, l’installation et la mise à jour de clients Flatpak
et OSTree épinglant la clé publique.

## Retours et assistance

Centraliser les problèmes d’installation, de mise à jour et d’utilisation dans
[Focale Community](https://github.com/focale-editor/community). Préciser la version
de Focale, la distribution Linux, la version de Flatpak et le message d’erreur.

Références : [héberger un dépôt Flatpak](https://docs.flatpak.org/en/latest/hosting-a-repository.html),
[GitHub Pages et les domaines personnalisés](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/about-custom-domains-and-github-pages).
