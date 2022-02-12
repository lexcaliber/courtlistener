BEGIN;
--
-- Create model Parenthetical
--
CREATE TABLE "search_parenthetical" ("id" serial NOT NULL PRIMARY KEY, "text" text NOT NULL, "usefulness_score" double precision NOT NULL, "described_opinion_id" integer NOT NULL, "describing_opinion_id" integer NOT NULL);
ALTER TABLE "search_parenthetical" ADD CONSTRAINT "search_parenthetical_described_opinion_id_ddd408db_fk_search_op" FOREIGN KEY ("described_opinion_id") REFERENCES "search_opinion" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_parenthetical" ADD CONSTRAINT "search_parenthetical_describing_opinion_i_07864494_fk_search_op" FOREIGN KEY ("describing_opinion_id") REFERENCES "search_opinion" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_parenthetical_usefulness_score_58a7adcf" ON "search_parenthetical" ("usefulness_score");
CREATE INDEX "search_parenthetical_described_opinion_id_ddd408db" ON "search_parenthetical" ("described_opinion_id");
CREATE INDEX "search_parenthetical_describing_opinion_id_07864494" ON "search_parenthetical" ("describing_opinion_id");
COMMIT;
