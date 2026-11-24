{
  description = "Jarvis LNX: NixOS + cage kiosk on Xiaomi Mi 11 Lite 4G (courbet)";

  # The inputs point at /work inside the build container (see scripts/handy-nixos-build.sh):
  #   /work/nixos-courbet  = git clone https://github.com/ElXreno/nixos-courbet
  #   /work/linux-c0f2fd4  = ElXreno/linux, branch courbet-7.3, commit c0f2fd4
  # Without the container use e.g. courbet.url = "github:ElXreno/nixos-courbet"; and drop the linux override.
  inputs = {
    courbet.url = "git+file:///work/nixos-courbet";
    # Lokal geholter, gepinnter Kernel-Commit c0f2fd4 (GitHub-Tarball war zu langsam)
    courbet.inputs.linux.url = "path:/work/linux-c0f2fd4";
    nixpkgs.follows = "courbet/nixpkgs";
  };

  outputs =
    { self, courbet, nixpkgs, ... }:
    let
      pkgsBuild = nixpkgs.legacyPackages.x86_64-linux;
      system = nixpkgs.lib.nixosSystem {
        modules = [
          courbet.nixosModules.default
          ./configuration.nix
          {
            # fetchpatch-Normalisierung (filterdiff) liefert unter qemu-user leere Ausgabe.
            # FODs sind systemunabhaengig -> x86-fetchpatch verwenden (gleiche Store-Pfade).
            nixpkgs.overlays = [ (final: prev: { fetchpatch = pkgsBuild.fetchpatch; }) ];
          }
        ];
      };
      toplevel = system.config.system.build.toplevel;
    in
    {
      nixosConfigurations.jarvis-handy = system;

      packages.x86_64-linux = {
        inherit toplevel;
        boot-img = courbet.lib.mkBootImg pkgsBuild toplevel;
        rootfs = system.config.system.build.rootfsImage;
      };
    };
}
