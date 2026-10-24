       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTUPD.
      *> Status update. Arg: 10-char account id followed by 1-char
      *> new status (A active, F frozen, C closed). Rewrites in place.
      *> RC 0 updated, 4 not found, 6 bad status, 8 file error.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-FILE ASSIGN TO ACCTFILE
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-FS.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-FILE.
       COPY ACCTREC.
       WORKING-STORAGE SECTION.
       01  WS-FS                   PIC XX.
       01  WS-ARG.
           05  WS-KEY              PIC X(10).
           05  WS-NEW              PIC X(1).
       01  WS-EOF                  PIC X VALUE "N".
       01  WS-FOUND                PIC X VALUE "N".
       PROCEDURE DIVISION.
           ACCEPT WS-ARG FROM COMMAND-LINE
           IF WS-NEW NOT = "A" AND WS-NEW NOT = "F"
              AND WS-NEW NOT = "C"
               MOVE 6 TO RETURN-CODE
               STOP RUN
           END-IF
           OPEN I-O ACCT-FILE
           IF WS-FS NOT = "00"
               MOVE 8 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM UNTIL WS-EOF = "Y" OR WS-FOUND = "Y"
               READ ACCT-FILE
                   AT END MOVE "Y" TO WS-EOF
                   NOT AT END
                       IF ACCT-ID = WS-KEY
                           MOVE "Y" TO WS-FOUND
                           MOVE WS-NEW TO ACCT-STATUS
                           REWRITE ACCT-REC
                       END-IF
               END-READ
           END-PERFORM
           CLOSE ACCT-FILE
           IF WS-FOUND = "Y"
               MOVE 0 TO RETURN-CODE
           ELSE
               MOVE 4 TO RETURN-CODE
           END-IF
           STOP RUN.
