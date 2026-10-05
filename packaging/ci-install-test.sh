#!/bin/bash
# CI kurulum testi: .deb'i kapsayıcıya kurar ve Linwas'ın açılabildiğini denetler.
# Başarısız olursa çıktının son satırlarını GitHub Actions hata notu (annotation) olarak yazar;
# böylece günlük dosyasına erişmeden de sorun okunabilir.
set -u

LOG=/tmp/linwas-install-test.log
: > "$LOG"
export DEBIAN_FRONTEND=noninteractive

run() {
    echo "+ $*" >> "$LOG"
    "$@" >> "$LOG" 2>&1
}

report_failure() {
    local title=$1
    # Annotation tek satır olmalı: satır sonları %0A ile kodlanır.
    local body
    body=$(tail -n 45 "$LOG" | sed -e 's/%/%25/g' -e 's/\r//g' | awk '{printf "%s%%0A", $0}')
    echo "::error title=${title}::${body}"
}

run apt-get update
status=0
run apt-get install -y ./linwas_*.deb || status=$?

if [ "$status" -ne 0 ]; then
    report_failure "apt kurulumu basarisiz"
    # Tanı için: bağımlılıkları zorlayarak kur ve uygulamanın kendisi açılıyor mu bak.
    echo "--- tani: bagimliliklar zorlanarak kurulum ---" >> "$LOG"
    run dpkg -i --force-depends ./linwas_*.deb || true
    run linwas --self-check || report_failure "self-check (bagimliliklar zorlanmis)"
    cat "$LOG"
    exit "$status"
fi

for args in "--version" "--self-check"; do
    if ! run linwas $args; then
        status=1
        report_failure "linwas $args basarisiz"
        break
    fi
done
if [ "$status" -eq 0 ] && ! LINWAS_LANG=en run linwas --self-check; then
    status=1
    report_failure "linwas --self-check (en) basarisiz"
fi

cat "$LOG"
exit "$status"
