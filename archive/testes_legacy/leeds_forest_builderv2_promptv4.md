# Teste: Leeds vs Forest (2026-02-06)
## Builder: v2 | Prompt: v4_calibrated
## RESULTADO REAL: 3-0 Leeds ✅

---

## STATUS

❌ **NÃO GERADO**

Builder v2 tem dados inconsistentes com a DB:
- Form strings desatualizadas
- Injuries potencialmente erradas
- Falta xG diff dos últimos 5 jogos

---

## CONTEXTO (resumo)

Builder v2 adicionou:
- H2H data
- Narratives (six_pointer, derby, stakes)
- Key injuries

Mas os dados de **form** estavam incorrectos, o que contamina qualquer análise.

---

## RECOMENDAÇÃO

Descartar builder v2 até:
1. Corrigir fonte de dados de form
2. Validar injuries contra dados reais
3. Adicionar xG diff aos últimos 5 jogos

**Próximo passo:** Usar builder v1 + form_interpreter.py (testado e funcionou)
